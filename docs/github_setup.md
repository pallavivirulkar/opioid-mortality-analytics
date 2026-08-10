# Pushing this project to GitHub

Run these from Terminal on your Mac, inside the project folder.

## 0. One-time cleanup

This folder was assembled in a sandboxed environment that left behind a
half-initialized, broken `.git` folder (a stuck lock file from that
environment — harmless on your machine, but needs clearing before you
init your own repo). Remove it first:

```bash
cd /path/to/opioid-mortality-hotspot-analysis
rm -rf .git
```

## 1. Initialize the repo and make the first commit

```bash
git init
git add -A
git commit -m "Initial commit: CDC WONDER opioid mortality hotspot analysis"
git branch -M main
```

## 2. Create the empty repo on GitHub

**Option A — website:**
1. Go to https://github.com/new
2. Repository name: `opioid-mortality-hotspot-analysis` (or whatever you prefer)
3. Choose Public or Private
4. **Do NOT** check "Add a README" / ".gitignore" / "license" — this repo
   already has all three, and initializing on GitHub too would create a
   conflicting history.
5. Click **Create repository**. Copy the repo URL it gives you
   (`https://github.com/<your-username>/<repo-name>.git`).

**Option B — GitHub CLI** (if you have `gh` installed and run `gh auth login` once):

```bash
gh repo create opioid-mortality-hotspot-analysis --public --source=. --remote=origin --push
```

This does steps 2 and 3 in one command — skip to done if you use this.

## 3. Connect and push (if you used Option A)

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

If prompted for a password over HTTPS: GitHub no longer accepts your
account password there. Use a **Personal Access Token** instead
(GitHub → Settings → Developer settings → Personal access tokens → generate
one with `repo` scope, then paste it as the password when prompted), or set
up an SSH key and use the `git@github.com:...` remote URL instead.

## 4. Verify

```bash
git log --oneline
git remote -v
```

Refresh the GitHub repo page in your browser — you should see all files,
and the CI workflow (`.github/workflows/ci.yml`) should kick off
automatically under the **Actions** tab.

## Later changes

```bash
git add -A
git commit -m "describe your change"
git push
```
