# vadd.s - vector addition:  C[i] = A[i] + B[i]   for i = 0 .. N-1
#
# Each loop pass handles one vector word, i.e. LANES elements at once.
# With 8 lanes the loop runs N/8 times; with 1 lane it runs N times.
# That difference is the whole SIMD speed-up.
#
# Constants filled in by run_workloads.py:
#   A, B, C : where each array starts in data memory (vector word address)
#   ITER    : loop passes = N / LANES

        ADDI s1, s0, 0          # s1 = word index, starts at 0
        ADDI s2, s0, ITER       # s2 = number of passes
loop:   VLD  v1, A(s1)          # v1 = next LANES elements of A
        VLD  v2, B(s1)          # v2 = next LANES elements of B
        VADD v3, v1, v2         # all lanes add at the same time
        VST  v3, C(s1)          # write LANES results to C
        ADDI s1, s1, 1          # move to the next word
        BNE  s1, s2, loop       # repeat until every word is done
        HALT
