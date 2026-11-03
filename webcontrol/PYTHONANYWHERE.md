# Free PythonAnywhere setup

PythonAnywhere can host this Flask control API on its free web-app subdomain over HTTPS. The free account includes one web app, one worker, 512 MiB of disk, and a one-month web-app expiry. The app database will be kept in your home directory, so it survives normal app reloads. Visit the Web page and renew the app when PythonAnywhere shows that it is expiring. Keep this for a small hobby control panel, not a high-traffic production service.

## 1. Create the free account

1. Sign up at https://www.pythonanywhere.com/registration/register/beginner/.
2. Choose the Free/Beginner account.
3. Open the Dashboard and start a Bash console.
4. In the Web tab choose Add a new web app, choose the free PythonAnywhere domain, then Manual configuration and Python 3.13.

## 2. Download the project and install dependencies

In the Bash console, paste:

    git clone --depth 1 https://github.com/swayangshree8-maker/resume-card-studio.git
    cd ~/resume-card-studio
    mkdir -p data

Use the Bash console with the same Python version you selected in the Web tab:

    python3.13 -m pip install --user -r requirements.txt
    python3.13 -m webcontrol.app hash-password
    python3.13 -c "import secrets; print(secrets.token_urlsafe(48))"

The hash-password command asks you to enter a new admin password and prints its hash. Copy the hash and the separate random token value somewhere private for the next step. Do not send either value here or commit them to GitHub.

## 3. Create the Flask web app

1. Open the WSGI configuration file shown on the Web tab, replace its contents with this template, and replace every placeholder. The WSGI file is private to your PythonAnywhere account; keep the secrets there only.

    import os
    import sys

    project_home = "/home/YOUR_PYTHONANYWHERE_USERNAME/resume-card-studio"
    if project_home not in sys.path:
        sys.path.insert(0, project_home)

    os.environ["ADMIN_USERNAME"] = "sway"
    os.environ["ADMIN_PASSWORD_HASH"] = "PASTE_THE_PASSWORD_HASH"
    os.environ["TOKEN_SECRET"] = "PASTE_THE_RANDOM_TOKEN_VALUE"
    os.environ["DATABASE_PATH"] = project_home + "/data/control.sqlite3"

    from webcontrol.app import app as application

2. Save the WSGI file. Return to the Web tab and press Reload.
3. Open your PythonAnywhere HTTPS address and add /api/health. It should show configured: true.

The username for the private control panel is sway. Sign in using the password you entered when generating the hash.

## 4. Connect the GitHub Pages website

Send the exact HTTPS address shown on the PythonAnywhere Web tab. It is safe to share that public address; do not share your account password or the two secret values. The site's API URL and Content Security Policy still need that address before the mobile control page can connect.

## Update the backend later

In a PythonAnywhere Bash console:

    cd ~/resume-card-studio
    git pull

Then use the Web tab's Reload button. Do not run git clean or delete the data directory; it contains settings and analytics.
