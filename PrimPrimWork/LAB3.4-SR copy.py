# Write a C++ or Python program to compute the sum of two given integer values. If
# the two values are the same, then return the square of their sum.
# Simon R COMCS230 Lab 3 question 4


def sum_or_square(a, b):
    if a == b:
        return (a + b) ** 2
    else:
        return a + b


if __name__ == '__main__':
    print("'00' x2 to end...")
    while True:
        a = input('Enter a number: ')
        b = input('Enter another number: ')
        if a == "00" and b == "00":
            break
        print(sum_or_square(int(a), int(b)))
        print("__________________")
