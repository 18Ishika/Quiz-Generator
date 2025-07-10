import streamlit as st
import pandas as pd
import json
import time
from generator import QuestionGenerator
import os

class QuizManager:
    def __init__(self):
        self.questions = []
        self.user_answers = []
        self.results = []
        self.last_generation_time = 0
        self.min_generation_interval = 5  # Minimum 5 seconds between generations

    def can_generate_new_quiz(self):
        """Prevent rapid-fire API calls"""
        current_time = time.time()
        return (current_time - self.last_generation_time) >= self.min_generation_interval

    def generate_questions(self, generator, topic, question_type, difficulty, num_question):
        """Generate questions with better error handling and reduced API calls"""
        
        # Check rate limiting
        if not self.can_generate_new_quiz():
            remaining_time = self.min_generation_interval - (time.time() - self.last_generation_time)
            st.warning(f"Please wait {remaining_time:.1f} seconds before generating a new quiz.")
            return False

        # Reset state
        self.questions = []
        self.user_answers = []
        self.results = []
        self.last_generation_time = time.time()

        try:
            # Reduced retry attempts to save API quota
            max_attempts = num_question + 2  # Much more conservative
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
                    if question_type == "Multiple Choice":
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
                    else:
                        question = generator.generate_fill_blank(topic, difficulty.lower())
                        question_text = question.question.strip().lower()
                        
                        if question_text not in generated_questions:
                            generated_questions.add(question_text)
                            self.questions.append({
                                'type': 'Fill in the Blank',
                                'question': question.question,
                                'answer': question.answer
                            })
                            
                    # Small delay to prevent overwhelming the API
                    time.sleep(0.5)
                    
                except Exception as gen_error:
                    st.warning(f"Failed to generate question: {gen_error}")
                    # Don't continue on repeated failures
                    if attempts >= 3:
                        break
                    continue
                        
            # Clean up progress indicators
            progress_bar.empty()
            status_text.empty()
            
            if len(self.questions) < num_question:
                st.warning(f"Generated {len(self.questions)} unique questions out of {num_question} requested. This helps conserve your API quota.")
                
        except Exception as e:
            st.error(f"Error generating questions: {e}")
            return False
        
        return len(self.questions) > 0
    
    def attempt_quiz(self):
        if not self.questions:
            st.warning("No questions generated yet!")
            return False
        
        st.header("📝 Quiz Time!")
        
        if not self.user_answers:
            self.user_answers = [None] * len(self.questions)
        
        for i, q in enumerate(self.questions):
            st.subheader(f"Question {i + 1}")
            st.write(q['question'])
            
            if q['type'] == 'MCQ':
                selected_option = st.radio(
                    "Choose your answer:",
                    q['options'],
                    key=f"mcq_{i}",
                    index=None if self.user_answers[i] is None else q['options'].index(self.user_answers[i]) if self.user_answers[i] in q['options'] else None
                )
                self.user_answers[i] = selected_option
                
            else:
                user_input = st.text_input(
                    "Enter your answer:",
                    value=self.user_answers[i] if self.user_answers[i] is not None else "",
                    key=f"fill_{i}"
                )
                self.user_answers[i] = user_input
            
            st.divider()
        
        return True
    
    def calculate_results(self):
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
            else:
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
        score, total = self.calculate_results()
        if not self.results:
            st.warning("No results to display!")
            return
        
        percentage = (score / total) * 100
        
        st.header("📊 Quiz Results")
        
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

    def save_quiz_to_cache(self, topic, question_type, difficulty):
        """Save generated quiz to session state cache"""
        cache_key = f"{topic}_{question_type}_{difficulty}"
        if 'quiz_cache' not in st.session_state:
            st.session_state.quiz_cache = {}
        
        st.session_state.quiz_cache[cache_key] = {
            'questions': self.questions,
            'timestamp': time.time()
        }

    def load_quiz_from_cache(self, topic, question_type, difficulty):
        """Load quiz from cache if available and recent"""
        cache_key = f"{topic}_{question_type}_{difficulty}"
        if 'quiz_cache' not in st.session_state:
            return False
        
        if cache_key in st.session_state.quiz_cache:
            cached_data = st.session_state.quiz_cache[cache_key]
            # Use cached data if less than 10 minutes old
            if time.time() - cached_data['timestamp'] < 600:
                self.questions = cached_data['questions']
                self.user_answers = []
                self.results = []
                return True
        
        return False


def main():
    st.set_page_config(
        page_title="AI Quiz Generator",
        page_icon="🧠",
        layout="wide"
    )
    
    st.title("🧠 AI Quiz Generator")
    st.markdown("Generate and take quizzes on any topic using AI! (Optimized for API efficiency)")
    
    # Initialize session state
    if 'quiz_manager' not in st.session_state:
        st.session_state.quiz_manager = QuizManager()
    
    if 'quiz_generated' not in st.session_state:
        st.session_state.quiz_generated = False
    
    if 'quiz_submitted' not in st.session_state:
        st.session_state.quiz_submitted = False
    
    # API Usage Warning
    st.info("💡 **API Usage Optimization**: This app now includes rate limiting and caching to preserve your API quota.")
    
    with st.sidebar:
        st.header("⚙️ Quiz Configuration")
        
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
            max_value=5,  # Reduced max to save API quota
            value=3
        )
        
        # Check if we can generate
        can_generate = st.session_state.quiz_manager.can_generate_new_quiz()
        
        if not can_generate:
            remaining_time = st.session_state.quiz_manager.min_generation_interval - (time.time() - st.session_state.quiz_manager.last_generation_time)
            st.warning(f"Rate limit: Wait {remaining_time:.1f}s")
        
        if st.button("🎯 Generate Quiz", type="primary", disabled=not can_generate):
            if not topic:
                st.error("Please enter a topic!")
            else:
                # Check cache first
                if st.session_state.quiz_manager.load_quiz_from_cache(topic, question_type, difficulty):
                    st.session_state.quiz_generated = True
                    st.session_state.quiz_submitted = False
                    st.success("Quiz loaded from cache! (No API call made)")
                    st.rerun()
                else:
                    # Generate new quiz
                    with st.spinner("Generating quiz questions..."):
                        try:
                            generator = QuestionGenerator()
                            success = st.session_state.quiz_manager.generate_questions(
                                generator, topic, question_type, difficulty, num_questions
                            )
                            
                            if success:
                                st.session_state.quiz_manager.save_quiz_to_cache(topic, question_type, difficulty)
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
    
    # Main content area
    if not st.session_state.quiz_generated:
        st.info("👈 Configure your quiz settings in the sidebar and click 'Generate Quiz' to start!")
    
        st.markdown("""
        ### 🚀 Optimized Features:
        - **Rate Limiting**: Prevents excessive API calls
        - **Caching**: Reuses recent quizzes to save API quota
        - **Conservative Retries**: Reduces failed generation attempts
        - **Progress Tracking**: Shows generation progress
        - **Smart Delays**: Prevents API overwhelming
        
        ### How to use:
        1. **Enter a topic** you want to be quizzed on
        2. **Choose question type** (Multiple Choice or Fill in the Blank)
        3. **Select difficulty level** (Easy, Medium, or Hard)
        4. **Set number of questions** (1-5, reduced to save quota)
        5. **Click 'Generate Quiz'** to create your personalized quiz
        6. **Answer the questions** and submit to see your results!
        """)
    
    elif not st.session_state.quiz_submitted:
        st.session_state.quiz_manager.attempt_quiz()
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("📤 Submit Quiz", type="primary", use_container_width=True):
                unanswered = []
                for i, (question, answer) in enumerate(zip(st.session_state.quiz_manager.questions, st.session_state.quiz_manager.user_answers)):
                    if question['type'] == 'MCQ':
                        if answer is None:
                            unanswered.append(i + 1)
                    else:
                        if not answer or answer.strip() == "":
                            unanswered.append(i + 1)
                
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