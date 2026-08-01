# CODE V7-A.1 Corrective Record

This record identifies the exact correction applied after review of the Waldorf
Microwave II/XT SysEx appendix.

```text
Corrected item 1 : WAVD sample interpretation
Previous         : raw byte interpreted directly as two's-complement int8
Correct          : raw byte XOR 80h, then interpret as signed int8

Corrected item 2 : 64-to-128 architecture
Previous         : architecture treated as unresolved hypothesis
Correct          : documented sign-inverted reverse second half

Still unresolved : exact physical treatment of negating -128
Safe policy      : normal generation restricted to -127..+127
```

CODE V7-A.1 supersedes every schema-1 gate manifest and every hardware probe generated
by the original CODE V7-A files. Those packages must not be transmitted.
