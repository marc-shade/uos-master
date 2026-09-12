/*
 * claude-c128 client.
 *
 * Renders the bridge's wire protocol onto the C128's 80-column VDC screen and
 * sends keystrokes back. The C128 does no layout of its own: the Linux side
 * already decided what every cell should contain, so this is a thin, fast
 * applier of cell runs.
 *
 * The protocol is decoded by a resumable state machine because bytes arrive
 * from the NMI ring buffer in arbitrary chunks, and a command can be split
 * across two reads.
 */
/* Native uOS adaptation; upstream MIT notice: apps/claude/LICENSE. */
#include <stdint.h>
#define SCR_COLS 80
#define SCR_ROWS 25
#define HAS_PANEL 1
#define KEY_RESYNC 0x84
#define KEY_DESKTOP 0x8c /* F8; Escape remains available to Claude. */
#define MACHINE_NAME "c128"
#define N_READY (*(volatile unsigned char*)0x3d12)
extern volatile unsigned char native_quit;
extern unsigned char native_border;
unsigned char acia_open(void);
void native_video_begin(void);
void native_video_end(void);
void panel_clear(void);

/* --- hardware, implemented in c128hw.s ---------------------------------- */
extern unsigned char scrRow, scrCol, scrAttr, scrLen, scrChar;
extern unsigned char scrBuf[256];

void scr_init(void);
void scr_run(void);
void scr_fill(void);
void scr_clear(void);
void scr_place_cursor(void);
void scr_setglyph(void);
void scr_scroll(void);


void acia_shutdown(void);
unsigned char acia_avail(void);
unsigned char acia_get(void);
void acia_put(unsigned char b);
unsigned char kb_get(void);       /* KERNAL GETIN: PETSCII key, 0 if none */
void scr_mirror(void);            /* copy a VDC plane into mirrorBuf */
extern unsigned char mirrorBuf[2048];

/* --- protocol ----------------------------------------------------------- */
#define CMD_CLEAR   0x01
#define CMD_RUN     0x02
#define CMD_FILL    0x03
#define CMD_CURSOR  0x04
#define CMD_FRAME   0x05
#define CMD_BELL    0x06
#define CMD_PANEL   0x07
#define CMD_HELLO   0x08
#define CMD_BYE     0x09
#define CMD_GLYPH   0x0A
#define CMD_SCROLL  0x0B
#define BYE_MAGIC   0x5A

/* --- client -> server control ------------------------------------------- */
#define CLIENT_ESCAPE 0x00
#define CLIENT_RESYNC 0x01
#define CLIENT_BYE    0x02
#define CLIENT_CREDIT 0x03
/* Must match CREDIT_UNIT in server/protocol.py. */
#define CREDIT_UNIT   64


#define CURSOR_HIDE 0xFF

/* Parser states. Each command collects a fixed header, then a payload. */
enum {
    S_OPCODE,
    S_ARGS,
    S_PAYLOAD,
    S_PANEL_PAYLOAD,
    S_GLYPH_PAYLOAD
};

static unsigned char state = S_OPCODE;
static unsigned char opcode;
static unsigned char args[4];
static unsigned char argsNeeded;
static unsigned char argsGot;
static unsigned char payloadNeeded;
static unsigned char payloadGot;
static unsigned char panelRow;
static unsigned char running = 1;
static unsigned char framesSeen;

/* Exported for the emulator harness: proves the main loop is alive. */
unsigned int loopCount;
static unsigned char consumed;
/* Host-settable: write 1 for characters or 2 for attributes and the main loop
   copies that VDC plane into mirrorBuf, then clears this back to 0. */
unsigned char mirrorReq;
unsigned char mirrorAddrHi, mirrorAddrLo;
static unsigned int retry;
/* Main-loop iterations since the last byte arrived. Wraps at 65536, which at
   roughly 20k iterations a second is a quiet link of a few seconds. */
static unsigned int idle;
unsigned int desyncs;   /* unrecognised opcodes seen */
/* Non-zero while a resync is outstanding; cleared when a frame arrives or the
   idle watchdog fires, so one desync cannot trigger a repaint storm. */
static unsigned char resyncCooldown;

#if HAS_PANEL
/* The 40-column VIC-II companion screen is written directly; it is small and
   updated rarely, so it does not need the VDC fast path. */
#define VIC_SCREEN ((unsigned char *)0x0400)
#define VIC_COLOR  ((unsigned char *)0xD800)

static unsigned char panelColor = 12;
static unsigned char panelOwned;   /* has the panel taken over the 40-col screen? */

static void panel_write(unsigned char row, unsigned char col, unsigned char code)
{
    unsigned int off = (unsigned int)row * 40u + col;
    if (row < 25 && col < 40) {
        VIC_SCREEN[off] = code;
        VIC_COLOR[off] = panelColor;
    }
}
#else
/* On the C64 that screen is the terminal itself. A panel line is accepted off
   the wire and discarded - writing it would overwrite the text the user is
   reading. The bridge does not send panels to a C64, so this is belt and
   braces against a mismatched pair. */
static void panel_write(unsigned char row, unsigned char col, unsigned char code)
{
    (void)row; (void)col; (void)code;
}
#endif

/* Main-loop passes left before the bell note is released. Counting down in the
   loop rather than spinning here keeps the receive path free: a blocking delay
   long enough to be audible would overrun the ACIA. */
static unsigned int bellTimer;
unsigned int bellCount;          /* exported so a test can prove it fired */

static void bell(void)
{
    /* A visual bell preserves SID ownership and write-only sound state. */
    *(volatile unsigned char*)0xd020 = 7;
    bellTimer = 6000;
    ++bellCount;
}

static void bell_tick(void)
{
    if (bellTimer && --bellTimer == 0)
        *(volatile unsigned char*)0xd020 = native_border;
}

/*
 * Ultimate II+ modem answering.
 *
 * The Ultimate presents a Hayes modem in front of the ACIA. When the bridge
 * dials in, it sends "\rRING\r" and waits for "ATA". Its replies are printable
 * ASCII plus CR, and protocol opcodes are $01-$09, so the two streams cannot
 * be confused: every byte can be offered to this watcher and to the protocol
 * decoder, and each ignores what belongs to the other.
 *
 * On a machine with no modem in front of the ACIA (VICE, or a real RS-232
 * cartridge) no RING ever arrives and this simply never fires.
 *
 * The caller only offers bytes that arrive between frames. That matters: the
 * screen codes for an uppercase "RING" are byte-identical to the modem's, so
 * scanning payload bytes would answer a call that never came. Gating on parser
 * state removes the ambiguity, which in turn makes it safe to re-arm on every
 * RING and reconnect automatically.
 */
/* Explicit ASCII, not char literals: cc65 maps 'R' to PETSCII $D2 for CBM
   targets, which could never match the $52 the modem actually sends. */
static const unsigned char RING[4] = { 0x52, 0x49, 0x4E, 0x47 };   /* "RING" */
static unsigned char ringMatch;
static unsigned char answered;

static void modem_watch(unsigned char b)
{
    if (b == RING[ringMatch]) {
        if (++ringMatch == 4) {
            static const unsigned char ata[4] = { 0x41, 0x54, 0x41, 0x0D };  /* "ATA" */
            unsigned char i;
            for (i = 0; i < 4; ++i)
                acia_put(ata[i]);
            /* A new call: forget the old session and ask for the screen again
               once the modem has gone transparent. */
            answered = 1;
            framesSeen = 0;
            retry = 0;
            ringMatch = 0;
        }
    } else {
        ringMatch = (b == RING[0]) ? 1 : 0;
    }
}

static void send_control(unsigned char code);

static void handle_byte(unsigned char b)
{
    switch (state) {
    case S_OPCODE:
        opcode = b;
        argsGot = 0;
        payloadGot = 0;
        switch (opcode) {
        case CMD_CLEAR:  argsNeeded = 1; break;
        case CMD_RUN:    argsNeeded = 4; break;
        case CMD_FILL:   argsNeeded = 5; break;
        case CMD_CURSOR: argsNeeded = 2; break;
        case CMD_PANEL:  argsNeeded = 3; break;
        case CMD_HELLO:  argsNeeded = 2; break;
        case CMD_GLYPH:  argsNeeded = 1; break;
        case CMD_SCROLL: argsNeeded = 3; break;
        case CMD_FRAME:  framesSeen = 1; resyncCooldown = 0; return;
        case CMD_BELL:   bell(); return;
        case CMD_BYE:    argsNeeded = 1; break;
        default:
            /* An unrecognised opcode means the stream is out of step. Ask for a
               repaint, which resynchronises the parser - but at most once per
               cooldown. Asking per stray byte turns one desync into a storm:
               every request costs a full 2KB repaint, which overruns the ring
               and produces more stray bytes. */
            ++desyncs;
            if (resyncCooldown == 0) {
                resyncCooldown = 1;
                send_control(CLIENT_RESYNC);
            }
            return;
        }
        state = S_ARGS;
        return;

    case S_ARGS:
        if (argsGot < sizeof(args))
            args[argsGot] = b;
        ++argsGot;
        if (argsGot < argsNeeded)
            return;

        switch (opcode) {
        case CMD_CLEAR:
            scrAttr = args[0];
            scr_clear();
            state = S_OPCODE;
            return;

        case CMD_RUN:
            scrRow = args[0];
            scrCol = args[1];
            scrAttr = args[2];
            payloadNeeded = args[3];
            if (payloadNeeded == 0) {
                state = S_OPCODE;
                return;
            }
            state = S_PAYLOAD;
            return;

        case CMD_FILL:
            /* args: row, col, attr, len, char - the char is the 5th byte, and
               args[] only holds four, so it arrives in `b`. */
            scrRow = args[0];
            scrCol = args[1];
            scrAttr = args[2];
            scrLen = args[3];
            scrChar = b;
            scr_fill();
            state = S_OPCODE;
            return;

        case CMD_CURSOR:
            scrRow = args[0];
            scrCol = args[1];
            scr_place_cursor();
            state = S_OPCODE;
            return;

        case CMD_GLYPH:
            /* args[0] is the character code; the 8 bitmap rows follow. */
            scrChar = args[0];
            payloadNeeded = 8;
            state = S_GLYPH_PAYLOAD;
            return;

        case CMD_SCROLL:
            /* args: top row, bottom row, count (bit 7 set = downward). The
               hardware layer moves the rows in place; the bridge repaints the
               rows the shift exposes in the same frame. */
            scrRow = args[0];
            scrCol = args[1];
            scrLen = args[2];
            scr_scroll();
            state = S_OPCODE;
            return;

        case CMD_PANEL:
#if HAS_PANEL
            if (!panelOwned) {
                /* First panel line: wipe the client's own startup text so the
                   companion screen is entirely the bridge's to draw. */
                panelOwned = 1;
                panel_clear();
            }
            panelColor = args[1] & 0x0F;
#endif
            panelRow = args[0];
            payloadNeeded = args[2];
            if (payloadNeeded == 0) {
                state = S_OPCODE;
                return;
            }
            state = S_PANEL_PAYLOAD;
            return;

        case CMD_BYE:
            /* A bare opcode would let one corrupted byte end the session, so
               the shutdown is confirmed by a magic byte. */
            if (b == BYE_MAGIC)
                running = 0;
            state = S_OPCODE;
            return;

        case CMD_HELLO:
        default:
            state = S_OPCODE;
            return;
        }

    case S_PAYLOAD:
        scrBuf[payloadGot] = b;
        ++payloadGot;
        if (payloadGot >= payloadNeeded) {
            scrLen = payloadNeeded;
            scr_run();
            state = S_OPCODE;
        }
        return;

    case S_PANEL_PAYLOAD:
        panel_write(panelRow, payloadGot, b);
        ++payloadGot;
        if (payloadGot >= payloadNeeded)
            state = S_OPCODE;
        return;

    case S_GLYPH_PAYLOAD:
        scrBuf[payloadGot] = b;
        ++payloadGot;
        if (payloadGot >= 8) {
            scr_setglyph();
            state = S_OPCODE;
        }
        return;
    }
}

static void send_control(unsigned char code)
{
    acia_put(CLIENT_ESCAPE);
    acia_put(code);
}

/* --- keyboard ----------------------------------------------------------- */
static void pump_keyboard(void)
{
    unsigned char k;
    /* GETIN returns PETSCII straight from the KERNAL buffer, or 0 when empty.
       Translation to terminal input happens on the Linux side. */
    while ((k = kb_get()) != 0) {
        if (k == KEY_DESKTOP) {
            running = 0;
            return;
        } else if (k == KEY_RESYNC) {
            /* Repaint from scratch, and re-arm the modem watcher so a bridge
               that has been restarted can ring us again. */
            state = S_OPCODE;
            framesSeen = 0;
            answered = 0;
            ringMatch = 0;
            retry = 0;
            send_control(CLIENT_RESYNC);
        } else if (k == CLIENT_ESCAPE) {
            continue;           /* $00 is reserved as the control escape */
        } else {
            acia_put(k);
        }
    }
}

/*
 * cc65 translates string literals to PETSCII for CBM targets, so text arriving
 * from C is PETSCII, not ASCII. The VDC stores screen codes, which are a
 * different encoding again; this is the standard PETSCII -> screen code fold.
 */
static unsigned char petscii_to_screen(unsigned char c)
{
    if (c < 0x20) return c + 0x80;
    if (c < 0x40) return c;                 /* space .. ?            */
    if (c < 0x60) return c - 0x40;          /* @A-Z  -> $00-$1F      */
    if (c < 0x80) return c - 0x20;          /* graphics              */
    if (c < 0xA0) return c + 0x40;
    if (c < 0xC0) return c - 0x40;
    if (c < 0xFF) return c - 0x80;
    return 0x5E;
}

static void splash(void)
{
    static const char *msg = "claude code / " MACHINE_NAME " - connecting";
    unsigned char i;
    for (i = 0; msg[i]; ++i)
        scrBuf[i] = petscii_to_screen((unsigned char)msg[i]);
    scrRow = 0;
    scrCol = 0;
    scrAttr = 0x0E;
    scrLen = i;
    scr_run();
}

void panel_clear(void)
{
    unsigned int i;
    for (i = 0; i < 1000; ++i) {
        VIC_SCREEN[i] = 0x20;
        VIC_COLOR[i] = 1;
    }
}

static void panel_text(unsigned char row, const char *text)
{
    unsigned char i;
    panelColor = 1;
    for (i = 0; text[i] && i < 40; ++i)
        panel_write(row, i, petscii_to_screen((unsigned char)text[i]));
}

static void landing(unsigned char error)
{
    static const char *lines[] = {
        "claude / uos", "", "claude code on your c128",
        "80-column terminal + 40-column status", "",
        "start the uos claude bridge on linux",
        "using your claude login and project.", "",
        "ultimate modem: de00/nmi, 38400 baud", "",
        "return: connect", "f8 or esc: desktop", "",
        "during session: help repaints",
        "f8 returns; esc goes to claude"
    };
    unsigned char row, i;
    scrAttr = 0x0e;
    scr_clear();
    panel_clear();
    for (row = 0; row < 15; ++row) {
        panel_text(row, lines[row]);
        for (i = 0; lines[row][i]; ++i)
            scrBuf[i] = petscii_to_screen((unsigned char)lines[row][i]);
        scrRow = row; scrCol = 0; scrLen = i; scr_run();
    }
    if (error) {
        const char *msg = error == 1 ? "serial port busy; close other session"
                                     : "serial port unavailable; check modem";
        panel_text(17, msg);
        for (i = 0; msg[i]; ++i) scrBuf[i] = petscii_to_screen((unsigned char)msg[i]);
        scrRow = 17; scrCol = 0; scrLen = i; scr_run();
    }
    scrRow = 255; scrCol = 255; scr_place_cursor();
}

int main(void)
{
    unsigned char budget;

    unsigned char key;
    native_video_begin();
    scrAttr = 0x0e;
    scr_init();
    landing(0);
    for (;;) {
        N_READY = 1;
        key = kb_get();
        if (key == KEY_DESKTOP || key == 27) {
            native_video_end();
            return 0;
        }
        if (key == 13) {
            N_READY = 0;
            key = acia_open();
            if (!key) break;
            landing(key);
        }
    }
    panel_clear();
    panel_text(0, "claude / uos");
    panel_text(2, "waiting for the linux bridge");
    panel_text(4, "80-column screen: terminal");
    panel_text(6, "help: repaint / reconnect");
    panel_text(7, "f8: return to desktop");
    splash();

    /* Only now is the NMI handler live. Anything the bridge sent while this
       machine was still loading is gone, so ask for the screen from scratch
       instead of starting from a partial picture. */
    consumed = 0;
    retry = 0;
    idle = 0;
    send_control(CLIENT_RESYNC);

    while (running && !native_quit) {
        N_READY = 1;
        ++loopCount;
        /* Re-announce until the server replies with a frame. The first attempt
           is lost whenever a modem is still in command mode, and on real
           hardware the operator may start this before the bridge exists. */
        if (!framesSeen && ++retry == 0)
            send_control(CLIENT_RESYNC);

        /* A frame cut off mid-payload leaves the parser stranded: it would read
           the next command's bytes as pixels and never resynchronise. If the
           link has been quiet that long and we are *not* between frames, the
           frame was truncated - reset and ask for a fresh screen.

           An idle link with the parser at rest is normal and must not trigger
           anything: repainting on a timer would flood a link this slow. */
        if (++idle == 0 && state != S_OPCODE) {
            state = S_OPCODE;
            framesSeen = 0;
            retry = 0;
        }
        /* Drain a bounded number of bytes before checking the keyboard, so a
           fast sender cannot starve input, and a burst still gets applied in
           one go rather than one byte per outer iteration. */
        if (mirrorReq) {
            if (mirrorReq == 4) {
                /* Diagnostic: run a full clear on demand, so the host can test
                   scr_clear in isolation from the protocol path. */
                scrAttr = 0x0E;
                scr_clear();
            } else if (mirrorReq == 5) {
                /* Read VDC RAM at the address in mirrorAddrHi/Lo. */
                scrChar = 3;
                scrRow = mirrorAddrHi;
                scrCol = mirrorAddrLo;
                scr_mirror();
            } else {
                scrChar = mirrorReq - 1;  /* 0 = characters, 1 = attributes */
                scr_mirror();
            }
            mirrorReq = 0;
        }
        bell_tick();
        budget = 255;
        while (budget-- && !native_quit && acia_avail()) {
            unsigned char b = acia_get();
            idle = 0;
            /* Every byte taken out of the ring is room the server may reuse.
               Acknowledging in units keeps the return traffic negligible while
               never letting the server run further ahead than the ring holds. */
            if (++consumed >= CREDIT_UNIT) {
                consumed = 0;
                send_control(CLIENT_CREDIT);
            }
            if (state == S_OPCODE)
                modem_watch(b);
            handle_byte(b);
            if (answered == 1) {
                /* Just answered the call. The modem is still parsing "ATA" and
                   has not gone transparent, so anything sent now is swallowed;
                   the retry below is what actually gets through. */
                answered = 2;
                state = S_OPCODE;
                retry = 0;
            }
        }
        pump_keyboard();
    }

    N_READY = 0;
    send_control(CLIENT_BYE);
    acia_shutdown();
    native_video_end();
    return 0;
}
