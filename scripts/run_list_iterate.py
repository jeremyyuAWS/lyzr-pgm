# scripts/run_list_iterate.py
import argparse
from src.services.agent_runner import create_and_run

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manager_yaml")
    parser.add_argument("usecases_file")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()

    result = create_and_run(args.manager_yaml, args.usecases_file,
                            save_outputs=args.save, push=args.push)
    print(result)

if __name__ == "__main__":
    main()
