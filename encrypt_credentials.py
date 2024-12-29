from cryptography.fernet import Fernet
import getpass

def main():
    # Generate a new encryption key
    encryption_key = Fernet.generate_key().decode()
    print("\nEncryption key (save this in your .env file):")
    print(f"ENCRYPTION_KEY={encryption_key}")
    
    # Initialize Fernet cipher with the new key
    cipher_suite = Fernet(encryption_key.encode())
    
    print("\nEnter your credentials to encrypt them:")
    
    # Bank of America Credentials
    print("\nBank of America Credentials:")
    bofa_user = input("Username: ")
    bofa_pass = getpass.getpass("Password: ")
    
    # Wells Fargo Credentials
    print("\nWells Fargo Credentials:")
    wf_user = input("Username: ")
    wf_pass = getpass.getpass("Password: ")
    
    # Encrypt all values
    print("\nEncrypted credentials (copy these to your .env file):")
    print(f"BOFA_USERNAME={cipher_suite.encrypt(bofa_user.encode()).decode()}")
    print(f"BOFA_PASSWORD={cipher_suite.encrypt(bofa_pass.encode()).decode()}")
    print(f"WELLS_FARGO_USERNAME={cipher_suite.encrypt(wf_user.encode()).decode()}")
    print(f"WELLS_FARGO_PASSWORD={cipher_suite.encrypt(wf_pass.encode()).decode()}")
    
    print("\nPlease copy these values to your .env file.")
    print("Keep your credentials and encryption key secure!")

if __name__ == "__main__":
    main()
