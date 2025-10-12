import streamlit as st
import pandas as pd
import json
import time
from generator import QuestionGenerator
import os

class QuizManager:
    def __init__(self):
        self.questions = []
        self.last_generation_time = 0
        self.min_generation_interval = 5  # seconds

    def can_generate_new_quiz(self):
        current_time = time.time()
        return (current_time - self.last_generation_time) >= self.min_generation_interval

    def generate_questions(self, generator, topic, difficulty, num_question):
        """Generate questions with better error handling and reduced API calls"""
        if not self.can_generate_new_quiz():
            remaining_time = self.min_generation_interval - (time.time() - self.last_generation_time)
            st.warning(f"Please wait {remaining_time:.1f} seconds before generating a new quiz.")
            return False

        self.questions = []
        self.last_generation_time = time.time()

        try:
            max_attempts = num_question + 2
            attempts = 0
            generated_questions = set()

            progress_bar = st.progress(0)
            status_text = st.empty()

            while len(self.questions) < num_question and attempts < max_attempts:
                attempts += 1

                # Update progress
                progress = len(self.questions) / num_question
                progress_bar.progress(progress)
                status_text.text(f"Generating question {len(self.questions) + 1}/{num_question}...")

                try:
                    question = generator.generate_mcq(topic, difficulty.lower())
                    question_text = question.question.strip().lower()

                    if question_text not in generated_questions:
                        generated_questions.add(question_text)
                        self.questions.append({
                            'type': 'MCQ',
                            'question': question.question,
                            'options': question.options,
                            'correct_answer': question.correct_answer
                        })

                    # Small delay to prevent overwhelming the API
                    time.sleep(0.5)

                except Exception as gen_error:
                    st.warning(f"Failed to generate question: {gen_error}")
                    if attempts >= 3:
                        break
                    continue

            progress_bar.empty()
            status_text.empty()

            if len(self.questions) < num_question:
                st.warning(f"Generated {len(self.questions)} unique questions out of {num_question} requested.")

        except Exception as e:
            st.error(f"Error generating questions: {e}")
            return False

        return len(self.questions) > 0

    def save_quiz_to_cache(self, topic, difficulty):
        """Save generated quiz to session state cache"""
        cache_key = f"{topic}_{difficulty}"
        if 'quiz_cache' not in st.session_state:
            st.session_state.quiz_cache = {}

        st.session_state.quiz_cache[cache_key] = {
            'questions': self.questions,
            'timestamp': time.time()
        }

    def load_quiz_from_cache(self, topic, difficulty):
        """Load quiz from cache if available and recent"""
        cache_key = f"{topic}_{difficulty}"
        if 'quiz_cache' not in st.session_state:
            return False

        if cache_key in st.session_state.quiz_cache:
            cached_data = st.session_state.quiz_cache[cache_key]
            # Use cached data if less than 10 minutes old
            if time.time() - cached_data['timestamp'] < 600:
                self.questions = cached_data['questions']
                return True

        return False


def main():
    st.set_page_config(
        page_title="AI Quiz Generator (Preview)",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("🧠 AI Quiz Generator — Step-by-step Preview")
    st.markdown("Generate quiz questions with AI and preview them step-by-step (no test-taking).")

    # Initialize session state
    if 'quiz_manager' not in st.session_state:
        st.session_state.quiz_manager = QuizManager()

    if 'quiz_generated' not in st.session_state:
        st.session_state.quiz_generated = False

    # Sidebar
    with st.sidebar:
        st.markdown("## ⚙️ Quiz Configuration")

        if not os.getenv("GOOGLE_API_KEY"):
            st.error("Please set your GOOGLE_API_KEY in the .env file")
            st.stop()

        st.markdown("### 📚 Topic Selection")
        topic = st.text_input(
            "Enter Quiz Topic:",
            placeholder="e.g., Python Programming, World History, Science",
            help="Enter any topic you want to preview questions for"
        )

        st.markdown("### 🎯 Difficulty Level")
        difficulty = st.selectbox(
            "Select Difficulty:",
            ["Easy", "Medium", "Hard"],
            help="Choose the difficulty level for your quiz questions"
        )

        st.markdown("### 🔢 Number of Questions")
        num_questions = st.slider(
            "Questions to Generate:",
            min_value=1,
            max_value=10,
            value=5,
            help="Select how many questions you want to generate"
        )

        st.markdown("---")

        # Check if we can generate
        can_generate = st.session_state.quiz_manager.can_generate_new_quiz()

        if not can_generate:
            remaining_time = st.session_state.quiz_manager.min_generation_interval - (time.time() - st.session_state.quiz_manager.last_generation_time)
            st.warning(f"⏱️ Rate limit: Wait {remaining_time:.1f}s")

        st.markdown("### 🚀 Generate Quiz (Preview)")
        if st.button("🎯 Generate Quiz", type="primary", disabled=not can_generate, use_container_width=True):
            if not topic:
                st.error("Please enter a topic!")
            else:
                # Check cache first
                if st.session_state.quiz_manager.load_quiz_from_cache(topic, difficulty):
                    st.session_state.quiz_generated = True
                    st.success("Quiz loaded from cache!")
                    st.session_state.current_q_idx = 0
                    st.rerun()
                else:
                    # Generate new quiz
                    with st.spinner("Generating quiz questions..."):
                        try:
                            generator = QuestionGenerator()
                            success = st.session_state.quiz_manager.generate_questions(
                                generator, topic, difficulty, num_questions
                            )

                            if success:
                                st.session_state.quiz_manager.save_quiz_to_cache(topic, difficulty)
                                st.session_state.quiz_generated = True
                                st.success("Quiz generated successfully!")
                                st.session_state.current_q_idx = 0
                                st.rerun()
                            else:
                                st.error("Failed to generate quiz!")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

        st.markdown("### 🔄 Reset")
        if st.button("🔄 Reset Quiz", use_container_width=True):
            st.session_state.quiz_manager = QuizManager()
            st.session_state.quiz_generated = False
            st.session_state.current_q_idx = 0
            st.rerun()

        st.markdown("---")
        st.markdown("### ℹ️ About")
        st.markdown("""
        This preview mode removes interactive test-taking. Use it to:
        - View generated questions one-by-one
        - Reveal correct answers when you want
        - Download the generated quiz as JSON for later use
        """)

    # Main content area
    if not st.session_state.quiz_generated:
        st.info("👈 Configure your quiz settings in the sidebar and click 'Generate Quiz' to preview questions step-by-step!")

        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown("""
            ### 🎯 How to Use Preview Mode
            1. Enter a topic in the sidebar
            2. Select difficulty (Easy, Medium, Hard)
            3. Choose number of questions (1-10)
            4. Click 'Generate Quiz' to create questions
            5. Use Previous / Next to move through questions
            6. Toggle 'Show correct answer' to reveal answers when needed
            """)

        with col2:
            st.markdown("""
            ### 📊 Features (Preview)
            - AI-generated questions (no test-taking)
            - Step-by-step viewer
            - Answer reveal on demand
            - Download quiz JSON
            """)

    else:
        qm = st.session_state.quiz_manager
        total = len(qm.questions)
        idx = st.session_state.get('current_q_idx', 0)
        idx = max(0, min(idx, total - 1))
        st.session_state.current_q_idx = idx

        st.header("🔍 Quiz Preview — Step by Step")
        st.subheader(f"Question {idx + 1} of {total}")

        q = qm.questions[idx]
        st.write(q['question'])

        st.markdown("**Options:**")
        for opt in q['options']:
            st.write(f"- {opt}")

        # Show correct answer toggle for current question
        show_answer_key = f"show_answer_{idx}"
        show_answer = st.checkbox("Show correct answer", key=show_answer_key)
        if show_answer:
            st.success(f"Correct Answer: {q['correct_answer']}")

        # Navigation buttons
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("⬅️ Previous", disabled=(idx == 0)):
                st.session_state.current_q_idx = max(0, idx - 1)
                st.rerun()

        with col2:
            if st.button("🔄 Restart Preview"):
                st.session_state.current_q_idx = 0
                st.rerun()

        with col3:
            if st.button("Next ➡️", disabled=(idx == total - 1)):
                st.session_state.current_q_idx = min(total - 1, idx + 1)
                st.rerun()

        st.markdown("---")
        # Download the entire quiz as JSON
        try:
            json_data = json.dumps(qm.questions, indent=2)
            st.download_button("📥 Download Quiz JSON", data=json_data, file_name=f"{topic}_{difficulty}_quiz.json", mime="application/json")
        except Exception:
            st.error("Failed to prepare download. Make sure questions exist.")

        # Option to generate a fresh quiz
        if st.button("🎯 Generate New Quiz", use_container_width=True):
            st.session_state.quiz_manager = QuizManager()
            st.session_state.quiz_generated = False
            st.session_state.current_q_idx = 0
            st.rerun()


if __name__ == "__main__":
    main()
