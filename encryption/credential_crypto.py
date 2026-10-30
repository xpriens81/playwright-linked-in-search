import binascii
from typing import Optional, Union
from cryptography.fernet import Fernet, InvalidToken

class CredentialError(ValueError):
    """A credential operation failed without exposing secret values."""

def cipher_key(key: Union[str, bytes]) -> Fernet:
    try:
        if isinstance(key, str):
            key = key.encode("ascii")
        return Fernet(key)
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise CredentialError("Invalid Fernet key") from None

def main(encrypt_decrypt: str= "", encrypt_decrypt_key: Union[str, bytes]= "", encrypt_decrypt_val: str= "") -> Optional[str]:
    """Print keys/ciphertext, return encrypted/decrypted text"""
    if encrypt_decrypt.strip().lower() == "key":
        return Fernet.generate_key().decode("ascii")
    if encrypt_decrypt not in ["encrypt", "decrypt"]:
        raise CredentialError("Action must be either encrypt, decrypt, key or empty")

    cipher = cipher_key(encrypt_decrypt_key)
    if encrypt_decrypt.strip().lower() == "encrypt":
        try:
            token = cipher.encrypt(encrypt_decrypt_val.encode("utf-8")).decode("ascii")
        except (UnicodeError, AttributeError):
            raise CredentialError("Plaintext must be a valid UTF-8 text") from None
        return token
    try:
        return cipher.decrypt(encrypt_decrypt_val.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, AttributeError, ValueError, TypeError):
        raise CredentialError("Cannot decrypt credentials") from None

if __name__ == "__main__":
    '''
        Run this method directly after setting your username and password in .cred file
        This will help generate a key and encrypt your credentials, so they are protected.
        
        If there is a key already generated, then the encryption will be ignored (to avoid overwriting)
        and doing a double-encryption
    '''
    from common.config import DECRYPTION_KEY, LINKEDIN_USER, LINKEDIN_PASSWORD, ENCODE_PROXY
    from common.config import set_key_to_file

    # If the DECRYPTION_KEY is set to KEY, generate a new key and encrypt the credentials
    # Once done, write the key to .key file, and encrypted credentials to .cred file
    key = DECRYPTION_KEY.strip()
    enc_user_name = enc_user_pwd = enc_proxy = ""
    if LINKEDIN_USER and LINKEDIN_PASSWORD:
        if DECRYPTION_KEY.strip().upper() == "KEY":
            print("Generating: Key and Credential Encryption.......")
            key = main(encrypt_decrypt="key", encrypt_decrypt_key="", encrypt_decrypt_val="")
            set_key_to_file("key", "DECRYPTION_KEY", key)
            if key:
                enc_user_name = main(
                    encrypt_decrypt="encrypt", encrypt_decrypt_key=f"{key}", encrypt_decrypt_val=f"{LINKEDIN_USER}"
                )
                enc_user_pwd = main(
                    encrypt_decrypt="encrypt", encrypt_decrypt_key=f"{key}", encrypt_decrypt_val=f"{LINKEDIN_PASSWORD}"
                )
                if ENCODE_PROXY:
                    enc_proxy = main(
                        encrypt_decrypt="encrypt", encrypt_decrypt_key=f"{key}", encrypt_decrypt_val=f"{ENCODE_PROXY}"
                    )
                    set_key_to_file("cred", "ENCODE_PROXY", enc_proxy)
                set_key_to_file("cred", "LINKEDIN_USER", enc_user_name)
                set_key_to_file("cred", "LINKEDIN_PASSWORD", enc_user_pwd)

        # Verify that it works fine - if a key already exists, then verify if the .cred file contains encrypted data
        print("")
        print("Validating: Key and Credential Encryption.......")
        try:
            if not (enc_user_name or enc_user_pwd):
                enc_user_name = LINKEDIN_USER
                enc_user_pwd = LINKEDIN_PASSWORD
            if not enc_proxy:
                enc_proxy = ENCODE_PROXY
            print(
                main(
                    encrypt_decrypt="decrypt", encrypt_decrypt_key=f"{key}", encrypt_decrypt_val=f"{enc_user_name}")
            )
            print(
                main(
                    encrypt_decrypt="decrypt", encrypt_decrypt_key=f"{key}", encrypt_decrypt_val=f"{enc_user_pwd}")
            )
            # If there was an encoding generated for PROXY (i.e. user is under a proxy)
            if enc_proxy:
                print(
                    main(
                        encrypt_decrypt="decrypt", encrypt_decrypt_key=f"{key}", encrypt_decrypt_val=f"{enc_proxy}")
                )
        except Exception as e:
            print(
                "Validation Failed: The encrypted credentials are corrupted. "
                "Re-process the key and credential generation. "
            )
            print(f"Validation Error: {e}")
    else:
        print("Note: Please add your UserName and Password in the .cred file, and then run this code again")
