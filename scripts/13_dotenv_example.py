import os
from dotenv import load_dotenv

def main():
    load_dotenv()  # reads .env in current directory
    print("MY_SECRET:", os.getenv("MY_SECRET", "<not set>"))

if __name__ == "__main__":
    main()

# Create a .env file with: MY_SECRET=hello to test
