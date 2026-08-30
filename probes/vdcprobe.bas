10 rem vdc probe v7: NO waits, correct address
100 for r=0 to 31
110 poke 54784,r
120 v=peek(54785)
130 print r;":";v;
140 next
150 print " done"
