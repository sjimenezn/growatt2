import os, git
r = git.Repo.clone_from(f"https://{os.getenv('GITHUB_PAT')}@github.com/sjimenezn/growatt2.git", "t")
with r.config_writer() as c: c.set_value("user", "name", "Bot"); c.set_value("user", "email", "b@x.com")
open("t/saved_data_test.json","w").write("TEST")
r.git.add("."); r.git.commit("-m","Update"); r.git.push()