MOD = 2187
freq = [0]*MOD
for a in range(1,730):
    r = pow(a,3,MOD)
    freq[r] += 1
N = 0
for r1 in range(MOD):
    f1 = freq[r1]
    if f1==0:
        continue
    for r2 in range(MOD):
        f2 = freq[r2]
        if f2==0:
            continue
        r3 = (-r1 - r2) % MOD
        f3 = freq[r3]
        if f3==0:
            continue
        N += f1*f2*f3
print("N =", N)
print("N mod 1000 =", N%1000)
