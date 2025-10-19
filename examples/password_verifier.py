def is_valid_password(password, min_length=8):
    common_passwords = ["Password123!", "Qwerty123!", "Admin123!"]
    if password in common_passwords:
        return False

    if (len(password) >= min_length and 
        any(char.isupper() for char in password) and 
        any(char.islower() for char in password) and 
        any(char.isdigit() for char in password) and
        any(not char.isalnum() for char in password) and
        not any(char.isspace() for char in password)):
        return True
    return False

def get_password_requirements(password):
    requirements = {
        "length": len(password) >= 8,
        "uppercase": any(char.isupper() for char in password),
        "lowercase": any(char.islower() for char in password),
        "digit": any(char.isdigit() for char in password),
        "special": any(not char.isalnum() and not char.isspace() for char in password),
    }
    return requirements

def get_password_strength(password):
    requirements = get_password_requirements(password)
    requirements_met = sum(requirements.values())
    if requirements_met == 5:
        return "strong"
    elif requirements_met >= 3:
        return "medium"
    elif requirements_met > 0:
        return "weak"
    else:
        return "not valid"