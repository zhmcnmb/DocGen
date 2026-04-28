import sys
from docgen.cli import run_new_session, run_resume_session


def main():
    if len(sys.argv) > 1:
        session_dir = sys.argv[1]
        run_resume_session(session_dir)
    else:
        run_new_session()


if __name__ == "__main__":
    main()
