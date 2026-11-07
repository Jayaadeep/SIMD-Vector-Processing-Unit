# dot.s - dot product:  s3 = A[0]*B[0] + A[1]*B[1] + ... + A[N-1]*B[N-1]
#
# VDOT multiplies the lanes and then the result combiner adds all the
# lane products into one number in the same instruction. The running total
# is kept in scalar register s3.
#
# Constants: A, B (array addresses), ITER (= N / LANES)

        ADDI s1, s0, 0          # s1 = word index
        ADDI s2, s0, ITER       # s2 = number of passes
        ADDI s3, s0, 0          # s3 = running total
loop:   VLD  v1, A(s1)
        VLD  v2, B(s1)
        VDOT s4, v1, v2         # s4 = sum of the LANES products
        ADD  s3, s3, s4         # add them to the total
        ADDI s1, s1, 1
        BNE  s1, s2, loop
        HALT
