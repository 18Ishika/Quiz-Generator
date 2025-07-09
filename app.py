import streamlit as st
import pandas as pd
import random 
from generator import QuestionGenerator
import os

class QuizManager:
    def __init__(self):
        self.questions = []
        self.user_answers = []
        self.results = []

    def generate_questions(self, generator, topic, question_type, difficulty, num_question):
        self.questions = []
        self.user_answers = []
        self.results = []

        try:
            for _ in range(num_question):
                # MCQ
                if question_type == "Multiple Choice":
                    question = generator.generate_mcq(topic, difficulty.lower())
                    self.questions.append({
                        'type': 'MCQ',
                        'question': question.question,
                        'options': question.options,
                        'correct_answer': question.correct_answer
                    })
                # Fill up
                else:
                    question = generator.generate_fill_blank(topic, difficulty.lower())
                    self.questions.append({
                        'type': 'Fill in the Blank',
                        'question': question.question,
                        'answer': question.answer
                    })
        except Exception as e:
            st.error(f"Error generating questions: {e}")
            return False
        return True
    
    def attempt_quiz(self):
        """Display quiz questions and collect user answers"""
        if not self.questions:
            st.warning("No questions generated yet!")
            return False
        
        st.header("📝 Quiz Time!")
        
        # Initialize user_answers if empty
        if not self.user_answers:
            self.user_answers = [None] * len(self.questions)
        
        # Display questions
        for i, q in enumerate(self.questions):
            st.subheader(f"Question {i + 1}")
            st.write(q['question'])
            
            if q['type'] == 'MCQ':
                # Multiple choice question
                selected_option = st.radio(
                    "Choose your answer:",
                    q['options'],
                    key=f"mcq_{i}",
                    index=None if self.user_answers[i] is None else q['options'].index(self.user_answers[i]) if self.user_answers[i] in q['options'] else None
                )
                self.user_answers[i] = selected_option
                
            else:  # Fill in the blank
                user_input = st.text_input(
                    "Enter your answer:",
                    value=self.user_answers[i] if self.user_answers[i] is not None else "",
                    key=f"fill_{i}"
                )
                self.user_answers[i] = user_input
            
            st.divider()
        
        return True
    
    def calculate_results(self):
        """Calculate quiz results"""
        if not self.questions or not self.user_answers:
            return False
        
        self.results = []
        score = 0
        
        for i, (question, user_answer) in enumerate(zip(self.questions, self.user_answers)):
            if question['type'] == 'MCQ':
                correct = user_answer == question['correct_answer']
                self.results.append({
                    'question_num': i + 1,
                    'question': question['question'],
                    'user_answer': user_answer,
                    'correct_answer': question['correct_answer'],
                    'correct': correct,
                    'type': 'MCQ'
                })
            else:  #
                correct = user_answer.lower().strip() == question['answer'].lower().strip() if user_answer else False
                self.results.append({
                    'question_num': i + 1,
                    'question': question['question'],
                    'user_answer': user_answer,
                    'correct_answer': question['answer'],
                    'correct': correct,
                    'type': 'Fill in the Blank'
                })
            
            if correct:
                score += 1
        
        return score, len(self.questions)
    
    def display_results(self):
        """Display quiz results"""
        if not self.results:
            st.warning("No results to display!")
            return
        
        score, total = self.calculate_results()
        percentage = (score / total) * 100
        
        st.header("📊 Quiz Results")
        
        # Display score
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Score", f"{score}/{total}")
        with col2:
            st.metric("Percentage", f"{percentage:.1f}%")
        with col3:
            if percentage >= 80:
                st.success("Excellent! 🎉")
            elif percentage >= 60:
                st.info("Good job! 👍")
            else:
                st.warning("Keep practicing! 💪")
        
        
        st.subheader("Detailed Results")
        
        for result in self.results:
            with st.expander(f"Question {result['question_num']} - {'✅ Correct' if result['correct'] else '❌ Incorrect'}"):
                st.write(f"**Question:** {result['question']}")
                st.write(f"**Your Answer:** {result['user_answer'] if result['user_answer'] else 'Not answered'}")
                st.write(f"**Correct Answer:** {result['correct_answer']}")
                
                if result['correct']:
                    st.success("Correct! ✅")
                else:
                    st.error("Incorrect ❌")


def main():
    st.set_page_config(
        page_title="AI Quiz Generator",
        page_icon="🧠",
        layout="wide"
    )
    
    st.title("🧠 AI Quiz Generator")
    st.markdown("Generate and take quizzes on any topic using AI!")
    
    if 'quiz_manager' not in st.session_state:
        st.session_state.quiz_manager = QuizManager()
    
    if 'quiz_generated' not in st.session_state:
        st.session_state.quiz_generated = False
    
    if 'quiz_submitted' not in st.session_state:
        st.session_state.quiz_submitted = False
    
    # Sidebar for quiz configuration
    with st.sidebar:
        st.header("⚙️ Quiz Configuration")
        t
        if not os.getenv("GOOGLE_API_KEY"):
            st.error("Please set your GOOGLE_API_KEY in the .env file")
            st.stop()
        
        topic = st.text_input("Enter Topic:", placeholder="e.g., Python Programming, World History")
        
        question_type = st.selectbox(
            "Question Type:",
            ["Multiple Choice", "Fill in the Blank"]
        )
        
        difficulty = st.selectbox(
            "Difficulty Level:",
            ["Easy", "Medium", "Hard"]
        )
        
        num_questions = st.slider(
            "Number of Questions:",
            min_value=1,
            max_value=10,
            value=5
        )
        
        if st.button("🎯 Generate Quiz", type="primary"):
            if not topic:
                st.error("Please enter a topic!")
            else:
                with st.spinner("Generating quiz questions..."):
                    try:
                        generator = QuestionGenerator()
                        success = st.session_state.quiz_manager.generate_questions(
                            generator, topic, question_type, difficulty, num_questions
                        )
                        
                        if success:
                            st.session_state.quiz_generated = True
                            st.session_state.quiz_submitted = False
                            st.success("Quiz generated successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to generate quiz!")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        
        if st.button("🔄 Reset Quiz"):
            st.session_state.quiz_manager = QuizManager()
            st.session_state.quiz_generated = False
            st.session_state.quiz_submitted = False
            st.rerun()
    
    if not st.session_state.quiz_generated:
        st.info("👈 Configure your quiz settings in the sidebar and click 'Generate Quiz' to start!")
    
        st.markdown("""
        ### How to use:
        1. **Enter a topic** you want to be quizzed on
        2. **Choose question type** (Multiple Choice or Fill in the Blank)
        3. **Select difficulty level** (Easy, Medium, or Hard)
        4. **Set number of questions** (1-10)
        5. **Click 'Generate Quiz'** to create your personalized quiz
        6. **Answer the questions** and submit to see your results!
        
        ### Features:
        - 🤖 AI-powered question generation
        - 📊 Instant results and scoring
        - 🎯 Multiple difficulty levels
        - 📝 Two question types available
        - 🔄 Easy quiz reset functionality
        """)
    
    elif not st.session_state.quiz_submitted:
        st.session_state.quiz_manager.attempt_quiz()
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("📤 Submit Quiz", type="primary", use_container_width=True):

                unanswered = [i + 1 for i, answer in enumerate(st.session_state.quiz_manager.user_answers) if not answer]
                
                if unanswered:
                    st.warning(f"Please answer all questions! Missing: {', '.join(map(str, unanswered))}")
                else:
                    st.session_state.quiz_submitted = True
                    st.rerun()
    
    else:
        st.session_state.quiz_manager.display_results()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Retake Quiz", use_container_width=True):
                st.session_state.quiz_submitted = False
                st.session_state.quiz_manager.user_answers = []
                st.rerun()
        
        with col2:
            if st.button("🎯 Generate New Quiz", use_container_width=True):
                st.session_state.quiz_manager = QuizManager()
                st.session_state.quiz_generated = False
                st.session_state.quiz_submitted = False
                st.rerun()


if __name__ == "__main__":
    main()