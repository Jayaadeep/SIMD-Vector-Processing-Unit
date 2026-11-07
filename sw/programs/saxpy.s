# saxpy.s - scaled vector addition:  Y[i] = a * X[i] + Y[i]
#
# "SAXPY" is a classic benchmark from linear algebra (BLAS). The number 'a'
# is the same for every element, so it lives in a scalar register and is
# broadcast to every lane (VMUL v1, v1, s3).
#
# Constants: X, Y (array addresses), ITER (= N / LANES), ALPHA (the number a)

        ADDI s1, s0, 0          # s1 = word index
        ADDI s2, s0, ITER       # s2 = number of passes
        ADDI s3, s0, ALPHA      # s3 = a
loop:   VLD  v1, X(s1)
        VLD  v2, Y(s1)
        VMUL v1, v1, s3         # every lane: X[i] * a   (a is broadcast)
        VADD v2, v1, v2         # every lane: + Y[i]
        VST  v2, Y(s1)          # overwrite Y with the result
        ADDI s1, s1, 1
        BNE  s1, s2, loop
        HALT
