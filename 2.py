a = int(input())
b = a // 100
c = a % 100
if b <= 12 and a >= 12:
    print("MMYY")
elif b >= 12 and a <= 12:
    print("YYMM")
elif a <=12 and b <=12:
    print("AMBIGUOUS")
else:
    print("NO")

print(b)
print(c)