def is_valid_password(password, min_length=8):
    common_passwords = ["Password123!", "Qwerty123!", "Admin123!"]
    if password in common_passwords:
        return False
    if len(password) < min_length:
        return False
    if not any(char.isupper() for char in password):
        return False
    if not any(char.islower() for char in password):
        return False
    if not any(char.isdigit() for char in password):
        return False
    if not any(not char.isalnum() for char in password):  # Check for special character
        return False
    if any(char.isspace() for char in password):  # Check for whitespace character
        return False
    return True

def get_password_requirements(password):
    requirements = {
        "length": False,
        "uppercase": False,
        "lowercase": False,
        "digit": False,
        "special": False
    }

    if len(password) >= 8:
        requirements["length"] = True
    if any(char.isupper() for char in password):
        requirements["uppercase"] = True
    if any(char.islower() for char in password):
        requirements["lowercase"] = True
    if any(char.isdigit() for char in password):
        requirements["digit"] = True
    if any(not char.isalnum() for char in password):
        requirements["special"] = True

    return requirements

def get_password_strength(password):
    requirements = get_password_requirements(password)
    met_requirements = sum(requirements.values())

    if met_requirements < 5:
        return "weak"

    length = len(password)
    if length >= 16:
        return "strong"
    elif length >= 12:
        return "medium"
    else:
        return "weak"

def is_valid_password_with_username(username, password):
    if not is_valid_password(password):
        return False
    
    # Converting both to lower case to make the check case-insensitive
    username_lower = username.lower()
    password_lower = password.lower()
    
    if username_lower in password_lower:
        return False
    
    return True

def is_password_in_history(password, history):
    return password in history