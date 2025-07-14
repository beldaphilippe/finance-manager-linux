#! /bin/sh

# # Function to run on Ctrl+C (SIGINT)
# function cleanup {
#     echo -e "\nEncrypting the database..."
#     gpg -r phil -e data.db && rm -f data.db
#     echo -e "Done."
#     exit 0
# }

# # Decrypt the database
# gpg -o data.db -d data.db.gpg && rm -f data.db.gpg

# # Set trap for SIGINT
# trap cleanup INT

firefox http://localhost:5000 &
python app.py
