# isa_test.s - runs EVERY vector instruction on random data
#
# This is the "nothing is left untested" program. Each loop pass loads two
# random vectors and then:
#   * runs all 14 ALU jobs as vector-vector ops  (V<op> v3, v1, v2)
#   * runs all 14 ALU jobs as vector-scalar ops  (V<op> v4, v1, s3)
#   * stores every result in its own memory area
#   * runs all 14 reduce ops and adds them into one checksum (s6)
#   * runs VDOT and keeps a separate running total (s7)
# The broadcast value s3 changes every pass, so shifts and compares see
# many different scalar values.
#
# Constants: A, B (inputs), OUT (first result area), STRIDE (size of each
#            area), ITER (= N / LANES)

        ADDI s1, s0, 0          # s1 = word index
        ADDI s2, s0, ITER       # s2 = number of passes
        ADDI s3, s0, 12345      # s3 = broadcast value (changes every pass)
        ADDI s6, s0, 0          # s6 = checksum of the reduce results
        ADDI s7, s0, 0          # s7 = running dot product
loop:   VLD  v1, A(s1)
        VLD  v2, B(s1)

        # ---- vector op vector ----
        VADD    v3, v1, v2
        VST     v3, OUT+0*STRIDE(s1)
        VSUB    v3, v1, v2
        VST     v3, OUT+1*STRIDE(s1)
        VAND    v3, v1, v2
        VST     v3, OUT+2*STRIDE(s1)
        VOR     v3, v1, v2
        VST     v3, OUT+3*STRIDE(s1)
        VXOR    v3, v1, v2
        VST     v3, OUT+4*STRIDE(s1)
        VSLL    v3, v1, v2
        VST     v3, OUT+5*STRIDE(s1)
        VSRL    v3, v1, v2
        VST     v3, OUT+6*STRIDE(s1)
        VSRA    v3, v1, v2
        VST     v3, OUT+7*STRIDE(s1)
        VMUL    v3, v1, v2
        VST     v3, OUT+8*STRIDE(s1)
        VSEQ    v3, v1, v2
        VST     v3, OUT+9*STRIDE(s1)
        VSLT    v3, v1, v2
        VST     v3, OUT+10*STRIDE(s1)
        VSLTU   v3, v1, v2
        VST     v3, OUT+11*STRIDE(s1)
        VMIN    v3, v1, v2
        VST     v3, OUT+12*STRIDE(s1)
        VMAX    v3, v1, v2
        VST     v3, OUT+13*STRIDE(s1)
        # ---- vector op broadcast scalar ----
        VADD    v4, v1, s3
        VST     v4, OUT+14*STRIDE(s1)
        VSUB    v4, v1, s3
        VST     v4, OUT+15*STRIDE(s1)
        VAND    v4, v1, s3
        VST     v4, OUT+16*STRIDE(s1)
        VOR     v4, v1, s3
        VST     v4, OUT+17*STRIDE(s1)
        VXOR    v4, v1, s3
        VST     v4, OUT+18*STRIDE(s1)
        VSLL    v4, v1, s3
        VST     v4, OUT+19*STRIDE(s1)
        VSRL    v4, v1, s3
        VST     v4, OUT+20*STRIDE(s1)
        VSRA    v4, v1, s3
        VST     v4, OUT+21*STRIDE(s1)
        VMUL    v4, v1, s3
        VST     v4, OUT+22*STRIDE(s1)
        VSEQ    v4, v1, s3
        VST     v4, OUT+23*STRIDE(s1)
        VSLT    v4, v1, s3
        VST     v4, OUT+24*STRIDE(s1)
        VSLTU   v4, v1, s3
        VST     v4, OUT+25*STRIDE(s1)
        VMIN    v4, v1, s3
        VST     v4, OUT+26*STRIDE(s1)
        VMAX    v4, v1, s3
        VST     v4, OUT+27*STRIDE(s1)
        # ---- reduce: add up all lanes of (v1 op v2) ----
        VREDADD  s5, v1, v2
        ADD     s6, s6, s5
        VREDSUB  s5, v1, v2
        ADD     s6, s6, s5
        VREDAND  s5, v1, v2
        ADD     s6, s6, s5
        VREDOR   s5, v1, v2
        ADD     s6, s6, s5
        VREDXOR  s5, v1, v2
        ADD     s6, s6, s5
        VREDSLL  s5, v1, v2
        ADD     s6, s6, s5
        VREDSRL  s5, v1, v2
        ADD     s6, s6, s5
        VREDSRA  s5, v1, v2
        ADD     s6, s6, s5
        VREDMUL  s5, v1, v2
        ADD     s6, s6, s5
        VREDSEQ  s5, v1, v2
        ADD     s6, s6, s5
        VREDSLT  s5, v1, v2
        ADD     s6, s6, s5
        VREDSLTU s5, v1, v2
        ADD     s6, s6, s5
        VREDMIN  s5, v1, v2
        ADD     s6, s6, s5
        VREDMAX  s5, v1, v2
        ADD     s6, s6, s5
        VDOT    s5, v1, v2
        ADD     s7, s7, s5
        ADDI    s3, s3, 1237    # new broadcast value for the next pass
        ADDI    s1, s1, 1
        BNE     s1, s2, loop
        HALT
