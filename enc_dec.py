from subprocess import run, CalledProcessError

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256  # <--- this is needed
from Crypto.Random import get_random_bytes

# GPG decryption using subprocess
def decrypt_gpg_file(input_path, output_path, passphrase):
    try:
        result = run(
            ['gpg', '--batch', '--yes',
             '--passphrase', passphrase,
             '--pinentry-mode', 'loopback',
             '-o', output_path, '-d', input_path],
            capture_output=True, check=True, text=True
        )
        return True, result.stdout
    except CalledProcessError as e:
        return False, e.stderr

# GPG encryption
def encrypt_gpg_file(in_file, out_file, password):
    try:
        run(
            ['gpg', '--batch', '--yes',
             '--passphrase', password,
             '--pinentry-mode', 'loopback',
             '-o', out_file, '-c', in_file],
            check=True
        )
    except CalledProcessError:
        raise Exception("Failed to encrypt file")

# encode a file
def encrypt_AES256(in_file, enc_file, password):
    # Read plaintext
    with open(in_file, "rb") as f:
        plaintext = f.read()

    # Generate salt and IV (16 bytes each)
    salt = get_random_bytes(16)
    iv = get_random_bytes(16)

    # Derive key using PBKDF2 (must match decoder exactly)
    key = PBKDF2(
        password,
        salt,
        dkLen=32,
        count=65536,
        hmac_hash_module=SHA256
    )

    # PKCS#7 padding
    pad_len = AES.block_size - (len(plaintext) % AES.block_size)
    padding = bytes([pad_len]) * pad_len
    padded_plaintext = plaintext + padding

    # Encrypt
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded_plaintext)

    # Write output: salt + iv + ciphertext
    with open(enc_file, "wb") as f:
        f.write(salt)
        f.write(iv)
        f.write(ciphertext)

# decrypt a file encoded with the java algorithm used in the android app
def decrypt_AES256(enc_file, out_file, password):
    with open(enc_file, "rb") as f:
        salt = f.read(16)
        iv = f.read(16)
        ciphertext = f.read()

    # PBKDF2 with SHA256 (matches Java)
    key = PBKDF2(password, salt, dkLen=32, count=65536, hmac_hash_module=SHA256)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(ciphertext)

    # Remove PKCS#7 padding
    pad_len = plaintext[-1]
    plaintext = plaintext[:-pad_len]

    with open(out_file, "wb") as f:
        f.write(plaintext)
