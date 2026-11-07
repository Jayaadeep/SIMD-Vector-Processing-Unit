# threshold.s - keep values at or above a limit, zero the rest:
#               Y[i] = X[i]  if X[i] >= T,  else 0
#
# This shows how SIMD handles an "if" without jumping: every lane builds a
# mask (all ones = keep, all zeros = drop) and ANDs its value with it.
#
#   mask = (X < T)          VSLT  -> all ones where X is below the limit
#   mask = NOT mask         VXOR with all ones (-1) flips every bit
#   Y    = X AND mask       keeps X where X >= T, gives 0 elsewhere
#
# Constants: X, Y (array addresses), ITER (= N / LANES), LIMIT (the value T)

        ADDI s1, s0, 0          # s1 = word index
        ADDI s2, s0, ITER       # s2 = number of passes
        ADDI s3, s0, LIMIT      # s3 = T
        ADDI s4, s0, -1         # s4 = all ones, used to flip the mask
loop:   VLD  v1, X(s1)
        VSLT v2, v1, s3         # mask: X < T
        VXOR v2, v2, s4         # flip it: X >= T
        VAND v3, v1, v2         # keep or clear each lane
        VST  v3, Y(s1)
        ADDI s1, s1, 1
        BNE  s1, s2, loop
        HALT
