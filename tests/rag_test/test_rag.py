from pathlib import Path
from datetime import datetime


from kegal.compile import compile_form_yaml_file
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

    validation_report = "# VALIDATIONS"

    invalid_outputs = "# INVALID OUTPUTS"

    report = "# RESULTS"
    for i, qe in enumerate(questions):
        question = qe["question"]
        validation = qe["validation"]

        test = f"## TEST[{i}]\n\n"
        report += test
        validation_report += test
        invalid_outputs += test

        report += f"### Question\n"
        report += f"- ***message***: {question}\n"

        expected_validation = f"- ***expected validation***: {validation}\n\n"
        report += expected_validation
        validation_report += expected_validation


        report += f"### Response\n"
        response = compile_form_yaml_file(Path("test_rag.yml"),
                                          message=question)
        for r in response:
            node_id = f"\n\n**{r.id}**\n"
            report += node_id

            prompt_size = r.prompt_size
            response_size = r.response_size
            report += f"- ***prompt size***: {prompt_size}\n"
            report += f"- ***response size***: {response_size}\n"

            response_content = r.response_content

            report += f"- ***validation***:\n"
            if "validation" in response_content:
                validation = response_content["validation"]
                report += f"validation: {validation}\n\n"
                validation_report += f"{node_id} validation: {validation}\n"
            else:
                report += "Invalid response content: no validation\n\n"
                invalid_outputs += f"{node_id} validation: failed\n"

            report += f"- ***response***:"
            if "response_txt" in response_content:
                report += response_content["response_txt"]
            elif "response_tool" in response_content:
                report += str(response_content["response_tool"])
            elif "response_obj" in response_content:
                report += (response_content["response_obj"])
            else:
                report += "Invalid response content: no response"
                invalid_outputs += f"{node_id} response failed\n"

            report += "\n---\n"

    save_markdown_report(REPORT_PATH, validation_report + "\n\n" + invalid_outputs + "\n\n" + report)