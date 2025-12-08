Why you saw that pip "dependency conflicts" message
- You installed packages into an environment that already contains other packages (for example, conda base).
- pip warns when installed package versions conflict with existing package requirements (it still installs, but versions may be incompatible).

Recommended fixes (pick one)
1) Use an isolated venv (recommended):
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   # If using Playwright:
   python -m playwright install

2) Use a dedicated conda environment:
   conda create -n scrapping python=3.11
   conda activate scrapping
   # prefer conda-forge for large binaries, then pip for leftovers:
   conda install -c conda-forge playwright
   pip install -r requirements.txt
   python -m playwright install

3) If you cannot isolate:
   - Manually resolve conflicts by pinning versions in requirements.txt to versions compatible with your environment (use pip check to see remaining conflicts).
   - Avoid mixing pip installs into the conda base environment.

Quick checks
- pip check   # lists broken dependencies after install
- pip show selenium  # verify package is installed in active env
- python -c "import selenium; print(selenium.__version__)"  # runs inside active env

Notes
- Installing into base environments often causes exactly these messages. Use a project-specific environment for reproducible, conflict-free installs.
