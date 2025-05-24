import os
import shutil
from git import Repo

# Minimal config
TOKEN = os.getenv("GITHUB_PAT")
REPO = f"https://{TOKEN}@github.com/sjimenezn/growatt2.git"

# Clone & setup
repo = Repo.clone_from(REPO, "temp_repo")
with repo.config_writer() as c:
    c.set_value("user", "name", "GitHub Uploader")
    c.set_value("user", "email", "uploader@example.com")

# Upload file
with open("temp_repo/saved_data_test.json", "w") as f:
    f.write("TEST")

# Push & clean
repo.git.add(".")
repo.git.commit("-m", "Update")
repo.git.push()
shutil.rmtree("temp_repo")
print("✅ Done")