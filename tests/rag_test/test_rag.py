from pathlib import Path
from datetime import datetime


from kegal.compile import compile_from_yaml_file
from kegal.llm.ollama_handler import OllamaHandler
from tests.rag_test.questions.questions import load_question_file_en, load_question_file_it
from tests.utils.reports import save_markdown_report

REPORT_PATH = Path(__file__).parent / "reports"


if __name__ == '__main__':
    print("test rag")
    # Create directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_name = f"chat_{timestamp}"


    questions_en = load_question_file_en()["questions"]
    questions_it = load_question_file_it()["questions"]

    questions = questions_en + questions_it

    general_report = {
        "output_failed": 0,
        "output_ok": 0,
    }
    reports = ""
    chats = ""

    for i, qe in enumerate(questions):
        question = qe["question"]
        validation = qe["validation"]

        # get response
        response = compile_from_yaml_file(Path("test_rag.yml"), message=question)

        reports += f"### TEST[{i}]\n"
        reports += f"- **expected validation**: {validation}\n"

        chats += f"### TEST[{i}]\n\n"
        chats += f"- **question**\n  {question}\n"

        chat_validations = []

        for r in response:
            agent_id = r.id
            prompt_size = r.prompt_size
            response_size = r.response_size
            response_content = r.response_content

            if "validation" in response_content:
                reports += f"- ***{agent_id} validation***: {response_content['validation']}\n"
                chat_validations.append(response_content["validation"])
            else:
                reports += f"- ***{agent_id} validation***: failed\n"
                general_report["output_failed"] += 1
                continue

            if "response_txt" in response_content:
                chats += f"- ***{agent_id} response***\n  {response_content['response_txt']}\n"
            elif "response_tool" in response_content:
                chats += f"- ***{agent_id} response***\n  ```json\n    {response_content['response_tool']}\n```\n"
            elif "response_obj" in response_content:
                chats += f"- ***{agent_id} response***\n  ```json\n    {response_content['response_obj']}\n```\n"
            else:
                chats += f"- ***{agent_id} response***\n  failed\n  {response_content}\n"
                general_report["output_failed"] += 1
                continue

            general_report["output_ok"] += 1
            chats += "\n---\n"
            reports += "\n---\n"


    REPORT_PATH.mkdir(parents=True, exist_ok=True)
    report = f"## RESUME\n\n"
    report += f"- **output_failed**: {general_report['output_failed']}\n"
    report += f"- **output_ok**: {general_report['output_ok']}\n"
    reports = report + "\n\n" + f"## REPORTS\n\n" + reports

    save_markdown_report(REPORT_PATH  / "reports", reports)
    save_markdown_report(REPORT_PATH  / "chats", chats)