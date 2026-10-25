# Publish on PythonAnywhere

This Flask app uses SQLite and stores uploaded resume/certificate files in
`static/uploads`. Keep the database and uploads private when transferring them;
the SQLite database can contain admin credentials and client enquiries.

## 1. Prepare the app files

Upload `app.py`, `requirements.txt`, the `templates` folder, the `static` folder,
and `portfolio.db` to a private directory in your PythonAnywhere account, for
example `/home/YOUR_USERNAME/portfolio`. Include any existing files under
`static/uploads` that you want to keep on the live site.

Do not publish `portfolio.db`, secrets, or private client data in a public
repository. Keep a backup of the database before deployment.

## 2. Create the PythonAnywhere web app

1. Create a PythonAnywhere account and open the **Web** tab.
2. Add a new **Manual configuration** app using a Python version supported by
   your account.
3. Create a virtual environment, for example
   `/home/YOUR_USERNAME/.virtualenvs/portfolio`.
4. In a PythonAnywhere Bash console, install dependencies:

   ```bash
   workon portfolio
   pip install -r /home/YOUR_USERNAME/portfolio/requirements.txt
   ```

   If you did not create the virtual environment with the name `portfolio`,
   activate it using its configured path instead of `workon portfolio`.

## 3. Configure the WSGI file

Open the WSGI configuration file shown in the PythonAnywhere **Web** tab and
set the app directory and secret key. Replace both placeholders with your own
values; do not commit this configuration to a public repository.

```python
import os
import sys

project_dir = "/home/YOUR_USERNAME/portfolio"
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

os.environ["SECRET_KEY"] = "PASTE_A_NEW_RANDOM_SECRET_HERE"

from app import app as application
```

Generate a secret key in a Bash console with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output into the WSGI configuration. Keep `portfolio.db` in the app
directory so the existing admin account and portfolio data are available.

## 4. Set up the live site

1. In the **Web** tab, set the source code directory to
   `/home/YOUR_USERNAME/portfolio`.
2. Set the virtualenv path to the virtual environment created above.
3. Check that the app directory contains `portfolio.db` and the required files
   under `static/uploads`.
4. Click **Reload** in the **Web** tab and open the assigned site URL.
5. Test the homepage, `/admin/login`, the resume, certificate images, and demo
   links. Change the admin password before sharing the site publicly.

To change the admin password from a PythonAnywhere Bash console, first change
to the app directory and activate its virtual environment. This prompts for the
new password without echoing it or putting it in shell history:

```bash
cd /home/YOUR_USERNAME/portfolio
workon portfolio
SECRET_KEY=temporary-console-key python - <<'PY'
import getpass
import app

with app.app.app_context():
    username = input("Admin username: ").strip()
    admin = app.Admin.query.filter_by(username=username).first()
    if admin is None:
        raise SystemExit("Admin account not found.")

    password = getpass.getpass("New password: ")
    confirmation = getpass.getpass("Confirm new password: ")
    if len(password) < 12 or password != confirmation:
        raise SystemExit("Passwords must match and contain at least 12 characters.")

    admin.password_hash = app.generate_password_hash(password)
    app.db.session.commit()
    print("Admin password updated.")
PY
```

PythonAnywhere's hosting plan determines custom-domain and outbound-network
features. Demo websites embedded in iframes may also be blocked by their own
hosting providers.
