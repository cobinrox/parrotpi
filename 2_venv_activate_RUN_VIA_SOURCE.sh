# use this to activate the venv
# WARNING WARNING YOU MUST RUN THIS SCRIPT LIKE THIS
# FROM THE COMMAND LINE:
#
# source 2_venv_activate.sh
echo "YOU MUST RUN THIS SCRIPT LIKE THIS: source 2_venv_activate.sh"
source venv/bin/activate || { echo "ERROR: run this with 'source 2_venv_activate.sh' (not ./2_venv_activate.sh)"; return 1; }
echo "Activated: $VIRTUAL_ENV"
