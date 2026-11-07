# relu.s - the ReLU function used in neural networks:  Y[i] = max(X[i], 0)
#
# Negative numbers become 0, positive numbers pass through unchanged.
# s0 is always 0, so "VMAX v2, v1, s0" compares every lane with zero.
#
# Constants: X, Y (array addresses), ITER (= N / LANES)

        ADDI s1, s0, 0          # s1 = word index
        ADDI s2, s0, ITER       # s2 = number of passes
loop:   VLD  v1, X(s1)
        VMAX v2, v1, s0         # every lane: max(X[i], 0)
        VST  v2, Y(s1)
        ADDI s1, s1, 1
        BNE  s1, s2, loop
        HALT
