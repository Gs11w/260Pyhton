# 3. Write Python program to calculate the volume of a cone. The users will input the
# Cone’s radius and the Cone’s height, these values will be store on local variables. Also,
# the program must use a global variable for PI and calculate the volume using the following
# volume formula: V = (1/3) ∗ Π ∗ R2 ∗ H

# Global PI
pi = 3.141592653589793


def getInput():  # Input from user
    rad = float(input("Enter the cone's radius: "))
    h = float(input("Enter the cone's height: "))
    rad = round(float(rad ** 2), 3)
    return rad, h


def getVolume(rad, high):  # Volume calculations
    volume = round(((1 / 3) * pi * rad * high), 3)
    return str(volume)


def printCone():  # Cone :)
    print("   ^   ")
    print("  / \\  ")
    print(" /   \\ ")
    print("/     \\")
    print("-------")


if __name__ == '__main__':
    userChoice = 'y'
    while userChoice == 'y':
        unitChoice = input("Units? y/n: ").lower()
        if unitChoice == "y":
            unit = input("Enter the unit ( in, cm, ft, mm): ")
        else:
            unit = ''
        radius, height = getInput()
        printCone()
        print("Volume: " + getVolume(radius, height) + unit)
        userChoice = input("Do you want to continue? y/n ").lower()
