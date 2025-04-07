from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np


from kegal.compile import compile_from_yaml_file
from tests.rag_test.questions.questions import load_question_file_en

REPORT_PATH = Path(__file__).parent / "reports"



class FailedMessagsReport:
    def __init__(self):
        self.content = ""

    def add_content(self, index: int, user_message: str, agent_message: str, log: str):
        self.content += f"## [{index}] Cause: {log} \n"
        self.content += f"- User: {user_message} \n"
        self.content += f"- Agent: {agent_message} \n"
        self.content += f"---\n"


    def save_markdown(self, save_path: Path):
        # Create file path and save content
        save_path = save_path.with_suffix(".md")
        save_path.write_text(self.content, encoding="utf-8")
        print(f"File saved to {save_path}")



class ValidationReport:
    def __init__(self):
        self.ok = 0
        self.failed = 0

    def plot_results(self, save_path=None, show=True):
        """
        Create a bar plot visualizing the ok and failed validation results.

        Args:
            save_path (str, optional): Path to save the plot image. If None, the plot isn't saved.
            show (bool, optional): Whether to display the plot. Defaults to True.

        Returns:
            tuple: The figure and axes objects for further customization if needed.
        """

        # Create the figure and axes
        fig, ax = plt.subplots(figsize=(10, 6))

        # Set up the data
        labels = ['Successful', 'Failed']
        values = [self.ok, self.failed]
        colors = ['#4CAF50', '#F44336']  # Green for successful, Red for failed

        # Create the bars
        bars = ax.bar(labels, values, color=colors, width=0.6)

        # Add values on top of the bars
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),  # 3 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=12)

        # Add title and labels
        ax.set_title('Validation Results', fontsize=16)
        ax.set_ylabel('Count', fontsize=12)
        ax.set_ylim(0, max(max(values), 1) * 1.1)  # Add some space above the bars

        # Add a grid for better readability
        ax.grid(axis='y', linestyle='--', alpha=0.7)

        # Calculate and display success rate
        total = self.ok + self.failed
        success_rate = (self.ok / total * 100) if total > 0 else 0
        plt.figtext(0.5, 0.01, f'Success Rate: {success_rate:.1f}%',
                    ha='center', fontsize=12, bbox={'facecolor': '#f0f0f0', 'alpha': 0.5, 'pad': 5})

        plt.tight_layout()

        # Save the plot if a path is provided
        if save_path:
            plt.savefig(save_path)
            print(f"Plot saved to {save_path}")

        # Show the plot if requested
        if show:
            plt.show()


if __name__ == '__main__':
    print("test rag")
    # Create directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = REPORT_PATH / f"report_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    questions = load_question_file_en()["questions"]


    response_output_report = ValidationReport()
    response_validation_report = ValidationReport()
    failed_messages = FailedMessagsReport()


    for i, qe in enumerate(questions):
        question = qe["question"]
        validation = qe["validation"]

        responses = compile_from_yaml_file(Path("test_rag.yml"), message=question)

        # check only last response
        response = responses[-1]
        agent_id = response.id
        prompt_size = response.prompt_size
        response_size = response.response_size
        response_content = response.response_content

        if "validation" in response_content:
            response_output_report.failed += 1
            failed_messages.add_content(i, question, response_content, "invalid output format")
        else:
            response_output_report.ok += 1
            continue

        if validation == False and  response_content["validation"] == False:
            response_validation_report.ok += 1
        elif validation == True and response_content["validation"] == True:
            response_validation_report.ok += 1
        else:
            response_validation_report.failed += 1
            if "response_txt" in response_content:
                failed_messages.add_content(i, question, response_content["response_txt"], "message validation failed")
            if "response_tool" in response_content:
                failed_messages.add_content(i, question, response_content["response_tool"], "tool invokation failed")

    response_output_report.plot_results(save_path=report_dir / "response_output_report.png", show=False)
    response_validation_report.plot_results(save_path=report_dir / "response_validation_report.png", show=False)
    failed_messages.save_markdown(save_path=report_dir / "failed_messages.md")