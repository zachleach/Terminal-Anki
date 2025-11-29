#!/usr/bin/env python3

# 2025.11.20, by @zachleach
# Python-based spaced repetition system with vim interface

import argparse
import hashlib
import os
import sqlite3
import subprocess
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path


# Spaced repetition intervals - days until next review after correct answer
SCHEDULE_INTERVALS_DAYS = [0, 1, 3, 7, 14, 28, 56]
DB_PATH = Path.home() / "anki" / "anki.db"


# Vim exit codes determine review outcome
QUIT, WRONG, EDIT, SKIP, CORRECT, UNDO = 0, 1, 2, 3, 4, 5


def compute_sha256_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def parse_question_answer_pair_chunks_from_file(file_path):
    """Parse file into chunks, where each chunk starts with a '?' line."""
    with open(file_path, 'r') as file_handle:
        content = file_handle.read()

    question_answer_pair_chunks = []
    current_chunk_lines = []

    for line in content.split('\n'):
        if line.startswith('?'):
            # New question found - save previous chunk if exists
            if current_chunk_lines:
                while current_chunk_lines and current_chunk_lines[-1] == '':
                    current_chunk_lines.pop()
                if current_chunk_lines:
                    question_answer_pair_chunks.append('\n'.join(current_chunk_lines))
            current_chunk_lines = [line]
        elif current_chunk_lines:
            # Continue accumulating lines for current question
            current_chunk_lines.append(line)

    # Handle final chunk
    if current_chunk_lines:
        while current_chunk_lines and current_chunk_lines[-1] == '':
            current_chunk_lines.pop()
        if current_chunk_lines:
            question_answer_pair_chunks.append('\n'.join(current_chunk_lines))

    return question_answer_pair_chunks


def initialize_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS schedule_info (
            question_hash TEXT PRIMARY KEY,
            due_date TEXT NOT NULL,
            review_date_index INTEGER NOT NULL
        );
    """)
    connection.commit()
    connection.close()


def get_due_date_and_schedule_index_from_database(question_hash):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.execute(
        "SELECT due_date, review_date_index FROM schedule_info WHERE question_hash = ?",
        [question_hash]
    )
    result = cursor.fetchone()
    connection.close()
    return result


def update_schedule_after_review(question_hash, review_result):
    """Single entry point for all review outcomes"""
    info = get_due_date_and_schedule_index_from_database(question_hash)
    # New cards start at index 1 (skip 0-day and 1-day intervals)
    # First correct answer will advance to index 2 (3-day interval)
    current_index = info[1] if info else 1
    today = datetime.now().date()

    if review_result == WRONG:
        new_index = 0
        due_date = today
    elif review_result == CORRECT:
        new_index = min(current_index + 1, len(SCHEDULE_INTERVALS_DAYS) - 1)
        due_date = today + timedelta(days=SCHEDULE_INTERVALS_DAYS[new_index])
    elif review_result == SKIP:
        new_index = current_index
        due_date = today

    connection = sqlite3.connect(DB_PATH)
    connection.execute(
        "INSERT OR REPLACE INTO schedule_info (question_hash, due_date, review_date_index) VALUES (?, ?, ?)",
        [question_hash, due_date.strftime("%Y-%m-%d"), new_index]
    )
    connection.commit()
    connection.close()


def is_question_due_for_review(question_hash):
    """New questions (not in DB) are always due."""
    info = get_due_date_and_schedule_index_from_database(question_hash)
    if info is None:
        return True
    due_date = datetime.strptime(info[0], "%Y-%m-%d").date()
    return due_date <= datetime.now().date()


def count_due_questions_in_file(file_path):
    """Count how many questions in the file are due for review today."""
    if not os.path.isfile(file_path):
        return 0

    chunks = parse_question_answer_pair_chunks_from_file(file_path)
    count = 0
    for chunk in chunks:
        question_line = chunk.split('\n')[0]
        question_hash = compute_sha256_hash(question_line)
        if is_question_due_for_review(question_hash):
            count += 1
    return count


def delete_orphaned_schedule_entries(anki_path):
    """Remove DB entries for questions that no longer exist in any file."""
    if not DB_PATH.exists():
        return

    anki_path = Path(anki_path)
    if not anki_path.exists():
        return

    # Collect all current question hashes from files
    current = set()
    for file_handle in anki_path.rglob('*.txt'):
        for question_answer_pair_chunk in parse_question_answer_pair_chunks_from_file(file_handle):
            current.add(compute_sha256_hash(question_answer_pair_chunk.split('\n')[0]))

    # Find and delete orphaned entries
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.execute("SELECT question_hash FROM schedule_info")
    db_hashes = set(row[0] for row in cursor.fetchall())

    for orphan_hash in db_hashes - current:
        connection.execute("DELETE FROM schedule_info WHERE question_hash = ?", (orphan_hash,))

    connection.commit()
    connection.close()


def display_due_questions_tree(path=None):
    """Show directory tree with due question counts appended to each file."""
    path = Path(path) if path else Path.home() / 'anki'

    if not path.exists():
        print(f"Path not found: {path}")
        return

    delete_orphaned_schedule_entries(path)

    if path.is_file():
        print(f"{path.name} {count_due_questions_in_file(path)}")
        return

    def walk_directory(directory, prefix=""):
        entries = [e for e in directory.iterdir()
                   if not e.name.startswith('.') and (e.is_dir() or e.suffix == '.txt')]
        entries = sorted(entries, key=lambda p: (p.is_file(), p.name))
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "

            if entry.is_dir():
                print(f"{prefix}{connector}{entry.name}/")
                walk_directory(entry, prefix + extension)
            else:
                count = count_due_questions_in_file(entry)
                print(f"{prefix}{connector}{entry.name} {count}")

    print(".")
    walk_directory(path)


def display_flashcard_in_vim(question_answer_pair_chunk, name=None):
    """Opens vim with question chunk and hides answer with 'ggjdG'. User reveals with ':earlier 9999h'. Exit code = review result."""
    cmd = ['vim', '-c', 'normal ggjdG']
    if name:
        cmd.extend(['-c', f'file {name}'])
    cmd.append('-')

    subprocess.run(['clear'])
    result = subprocess.run(cmd, input=question_answer_pair_chunk.encode())
    return result.returncode


def open_file_for_editing(file_path, question_line=None):
    """Open the source file in vim for editing, optionally at the question's line."""
    if question_line:
        # Use grep to find the line number
        result = subprocess.run(
            ['grep', '-n', '-F', '-m', '1', question_line, file_path],
            capture_output=True,
            text=True
        )
        if result.stdout:
            line_number = result.stdout.split(':')[0]
            subprocess.run(['vim', f'+{line_number}', '-c', 'normal zt', file_path])
        else:
            # Fallback if grep fails
            subprocess.run(['vim', file_path])
    else:
        subprocess.run(['vim', file_path])
    subprocess.run(['clear'])


def get_due_questions(question_answer_pair_chunks):
    """Filter chunks to only those due for review today."""
    due = []
    for chunk in question_answer_pair_chunks:
        question_line = chunk.split('\n')[0]
        if is_question_due_for_review(compute_sha256_hash(question_line)):
            due.append((question_line, chunk))
    return due


def review_due_questions(file_path):
    """Main review loop - presents due questions in vim and updates schedule."""
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return

    initialize_database()
    reviewed_hashes = set()  # Track questions already answered this session
    history_stack = []  # Track previous states for undo: [(hash, prev_state, question_data)]

    while True:
        # Re-parse file (fresh content after edits)
        question_answer_pair_chunks = parse_question_answer_pair_chunks_from_file(file_path)
        due = get_due_questions(question_answer_pair_chunks)

        # Filter out questions we've already reviewed this session
        due = [(q, c) for q, c in due
               if compute_sha256_hash(q) not in reviewed_hashes]

        if not due:
            if not reviewed_hashes:
                print("No due questions in this file.")
            subprocess.run(['clear'])
            return

        # Use deque for flexible card navigation
        due_deque = deque(due)

        while due_deque:
            question_line, question_answer_pair_chunk = due_deque.popleft()
            question_hash = compute_sha256_hash(question_line)
            exit_code = display_flashcard_in_vim(question_answer_pair_chunk, file_path)

            if exit_code == QUIT:
                subprocess.run(['clear'])
                return
            elif exit_code == EDIT:
                open_file_for_editing(file_path, question_line)
                break  # Exit inner loop to re-parse file
            elif exit_code == UNDO:
                if not history_stack:
                    subprocess.run(['clear'])
                    return  # No history - terminate session

                # Pop the last reviewed question
                prev_hash, prev_state, (prev_q_line, prev_chunk) = history_stack.pop()

                # Restore previous database state
                connection = sqlite3.connect(DB_PATH)
                if prev_state is None:
                    # Was a new question - remove from database
                    connection.execute("DELETE FROM schedule_info WHERE question_hash = ?", [prev_hash])
                else:
                    # Restore the old state
                    connection.execute(
                        "INSERT OR REPLACE INTO schedule_info (question_hash, due_date, review_date_index) VALUES (?, ?, ?)",
                        [prev_hash, prev_state[0], prev_state[1]]
                    )
                connection.commit()
                connection.close()

                # Remove from reviewed set so it can be shown again
                reviewed_hashes.discard(prev_hash)

                # Put current card back on the queue, then the previous card
                due_deque.appendleft((question_line, question_answer_pair_chunk))
                due_deque.appendleft((prev_q_line, prev_chunk))
            else:
                # Normal review outcomes (WRONG, CORRECT, SKIP)
                # Capture previous state before updating
                prev_state = get_due_date_and_schedule_index_from_database(question_hash)
                history_stack.append((question_hash, prev_state, (question_line, question_answer_pair_chunk)))

                update_schedule_after_review(question_hash, exit_code)
                reviewed_hashes.add(question_hash)
        else:
            # while-loop completed without break = all done
            subprocess.run(['clear'])
            return


def custom_study_all_questions(file_path):
    """Review all questions regardless of schedule, no DB updates."""
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return

    question_answer_pair_chunks = parse_question_answer_pair_chunks_from_file(file_path)
    if not question_answer_pair_chunks:
        print("No questions found in this file.")
        return

    print(f"Custom study mode: {len(question_answer_pair_chunks)} questions\n")
    for question_answer_pair_chunk in question_answer_pair_chunks:
        display_flashcard_in_vim(question_answer_pair_chunk, file_path)


def forget_file_schedule(file_path):
    """Remove all schedule entries for questions in a file."""
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return

    if not DB_PATH.exists():
        print("No database exists.")
        return

    chunks = parse_question_answer_pair_chunks_from_file(file_path)
    if not chunks:
        print("No questions found in this file.")
        return

    connection = sqlite3.connect(DB_PATH)
    deleted = 0
    for chunk in chunks:
        question_line = chunk.split('\n')[0]
        question_hash = compute_sha256_hash(question_line)
        cursor = connection.execute(
            "DELETE FROM schedule_info WHERE question_hash = ?",
            [question_hash]
        )
        deleted += cursor.rowcount

    connection.commit()
    connection.close()
    print(f"Forgot {deleted} question(s) from schedule.")


def main():
    parser = argparse.ArgumentParser(description="Spaced repetition with vim")
    parser.add_argument('file', nargs='?', help='File to review (or directory for due tree)')
    parser.add_argument('-f', metavar='FILE', dest='custom', help='Custom study (no DB updates)')
    parser.add_argument('--forget', metavar='FILE', help='Remove schedule entries for a file')

    args = parser.parse_args()

    # Priority 0: Forget mode (--forget flag)
    # Remove schedule entries for all questions in a file
    if args.forget:
        forget_file_schedule(args.forget)

    # Priority 1: Custom study mode (-f flag)
    # Reviews all questions in the file without updating the database
    elif args.custom:
        custom_study_all_questions(args.custom)

    # Priority 2: File or directory argument provided
    elif args.file:
        path = Path(args.file)
        # Directory: show tree with due counts
        if path.is_dir():
            display_due_questions_tree(args.file)
        # File: start spaced repetition review session
        else:
            review_due_questions(args.file)

    # Priority 3: No arguments - show due tree from ~/anki
    else:
        display_due_questions_tree()


if __name__ == "__main__":
    main()
