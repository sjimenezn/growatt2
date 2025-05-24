import os
import sys
from git import Repo

# Config
GITHUB_TOKEN = os.getenv("GITHUB_PAT")
if not GITHUB_TOKEN:
    print("❌ Set GITHUB_PAT environment variable first!")
    sys.exit(1)  # Exit with error code

REPO_URL = f"https://{GITHUB_TOKEN}@github.com/sjimenezn/growatt2.git"
FILE_NAME = "saved_data_test.json"

try:
    # Clone, setup identity, and push
    repo = Repo.clone_from(REPO_URL, "temp_repo")
    with repo.config_writer() as c:
        c.set_value("user", "name", "Koyeb Bot")
        c.set_value("user", "email", "bot@koyeb.com")
    
    with open(f"temp_repo/{FILE_NAME}", "w") as f:
        f.write("TEST " + os.urandom(4).hex())
    
    repo.git.add(FILE_NAME)
    repo.git.commit("-m", "Update test file")
    repo.git.push()
    
    print("✅ File uploaded successfully!")
    sys.exit(0)  # Clean exit

except Exception as e:
    print(f"❌ Failed: {str(e)}")
    sys.exit(1)  # Exit with error code