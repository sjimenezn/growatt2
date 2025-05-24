import os
import shutil
from git import Repo

# Config
TOKEN = os.getenv("GITHUB_PAT")
if not TOKEN:
    print("❌ Set GITHUB_PAT environment variable!")
    exit(1)

REPO = f"https://{TOKEN}@github.com/sjimenezn/growatt2.git"
FILE = "saved_data_test.json"

try:
    # Setup
    if os.path.exists("temp_repo"):
        shutil.rmtree("temp_repo")
    repo = Repo.clone_from(REPO, "temp_repo")
    
    # Configure git
    with repo.config_writer() as c:
        c.set_value("user", "name", "GitHub Uploader")
        c.set_value("user", "email", "uploader@example.com")

    # Modify file
    with open(f"temp_repo/{FILE}", "w") as f:
        f.write(f"TEST {os.urandom(4).hex()}")  # Unique content each run

    # Only commit if there are changes
    if repo.git.diff():
        repo.git.add(".")
        repo.git.commit("-m", "Update test file")
        repo.git.push()
        print("✅ Pushed changes to GitHub")
    else:
        print("⚠️ No changes to commit")

    shutil.rmtree("temp_repo")
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)