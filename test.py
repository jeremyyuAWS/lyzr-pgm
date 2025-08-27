from prefect.blocks.system import Secret


secret_block = Secret.load("lyzr-api-key")

# Access the stored secret
print(secret_block.get() ) # This will return the secret value