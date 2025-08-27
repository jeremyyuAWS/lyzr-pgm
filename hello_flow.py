from prefect import flow, task
from prefect import get_run_logger

@task
def say_hello(name: str):
    logger = get_run_logger()
    logger.info(f"Hello, {name}!")
    return f"Hello, {name}!"

@flow(name="Hello World Flow")
def hello_world_flow():
    logger = get_run_logger()
    logger.info("Starting the flow...")

    # run task
    greeting = say_hello("Jeremy")
    logger.info(f"Greeting result: {greeting}")

    logger.info("Flow complete ✅")

if __name__ == "__main__":
    hello_world_flow()
