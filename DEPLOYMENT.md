# Publish the portfolio

This Flask app uses SQLite and stores uploaded resume/certificate files in
the configured data directory. Keep the database and uploads private when
transferring them; the SQLite database can contain admin credentials and client
enquiries.

## Run locally on Windows

Open PowerShell in the project directory and set the initial admin credentials
before starting Flask. The app generates a private secret key in its data
directory when `SECRET_KEY` is not set:

```powershell
$env:ADMIN_USERNAME = "your-admin-name"
$env:ADMIN_PASSWORD = "replace-with-a-unique-strong-password"
python app.py
```

Keep the credentials private and do not commit them. On first startup, the app
creates the database and the admin account when both admin variables are set.
Open `http://127.0.0.1:5000/admin/login` and sign in with those credentials.
For production, set a long random `SECRET_KEY` in the hosting provider's
environment settings so sessions stay valid across instances and deployments.
The app does not change an existing admin password when these variables change;
use the password reset procedure below to update it.

## Render: keep projects, certificates, and resume after restart

Render's service filesystem is temporary unless a Persistent Disk is attached.
Without a disk, SQLite updates and uploaded files can disappear after a restart
or deploy.

1. In the Render Dashboard, open your web service and add a **Persistent Disk**
   with mount path `/var/data`. Persistent disks may require a paid service plan.
2. Under **Environment**, add `DATA_DIR` with value `/var/data`, set a strong
   random `SECRET_KEY`, and set `ADMIN_USERNAME` and `ADMIN_PASSWORD` if this
   is the first admin account.
3. Deploy the updated app. It stores the SQLite database (including live demo
   projects), certificate images, and uploaded resume under that directory.
4. In `/admin/login`, add a live demo under **Manage Portfolio Demos**; it
   appears in the public **Projects** section. Upload a resume or certificate,
   then reload the service and confirm the project and files remain.

The repository's bundled `static/uploads/resume/resume.pdf` is shown whenever
there is no uploaded replacement, so the public Resume section remains
available even after a service restart. To keep a resume uploaded through the
admin page across deploys and restarts, the Persistent Disk is required.

If your current SQLite database or uploaded images are only on Render's
temporary filesystem, back them up before changing the service or deploying.
The new persistent disk starts empty; upload the saved `portfolio.db` and files
into `/var/data` (keeping the `uploads/certificates` and `uploads/resume`
folders) before switching over. If the current data is already gone, add the
certificate again after the persistent disk is mounted.

If your Render plan does not support a Persistent Disk, use a managed database
and durable object/file storage instead; setting `DATA_DIR` alone does not make
temporary storage permanent.

## PythonAnywhere

## 1. Prepare the app files

Upload `app.py`, `requirements.txt`, the `templates` folder, the `static` folder,
to a private directory in your PythonAnywhere account, for example
`/home/YOUR_USERNAME/portfolio`. Put the database at
`/home/YOUR_USERNAME/.local/share/portfolio/portfolio.db` and existing uploaded
files in that data directory's `uploads` folder.

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
os.environ["DATA_DIR"] = "/home/YOUR_USERNAME/.local/share/portfolio"

from app import app as application
```

Create the data directory before reloading the web app. Keep the existing
`portfolio.db` and uploaded files there.

Generate a secret key in a Bash console with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output into the WSGI configuration.

## 4. Set up the live site

1. In the **Web** tab, set the source code directory to
   `/home/YOUR_USERNAME/portfolio`.
2. Set the virtualenv path to the virtual environment created above.
3. Check that `DATA_DIR` contains `portfolio.db` and the required files under
   `uploads`.
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
import os
os.environ["DATA_DIR"] = "/home/YOUR_USERNAME/.local/share/portfolio"
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
