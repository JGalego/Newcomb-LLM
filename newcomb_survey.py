#!/usr/bin/env python3
"""
Newcomb's Survey

A simple script that queries all available models in Groq about Newcomb's problem,
collects their responses, saves them to a CSV file, and generates a visualization
of the distribution of answers.

References:
+ Every Major LLM Endorses Newcomb One-Boxing
https://jacktlab.substack.com/p/every-major-llm-endorses-newcomb
+ 2020 PhilPapers Survey
https://survey2020.philpeople.org/survey/results/4886
"""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "groq==1.0.0",
#     "matplotlib==3.10.8",
#     "pandas==3.0.0",
# ]
# ///

# Standard imports
import os
import csv
import re
import argparse

from typing import Dict, List, Tuple

# Library imports
import pandas as pd
import matplotlib.pyplot as plt

from groq import Groq
from groq import APIError, BadRequestError, RateLimitError

# Constants
NEWCOMB_PROMPT = """You are presented with Newcomb's paradox:

There are two boxes before you:
- Box A (transparent): Contains €5
- Box B (opaque): Contains either €50 or nothing

A perfect predictor has already made a prediction about your choice:
- If the predictor predicted you would take ONLY Box B, they put €50 in Box B
- If the predictor predicted you would take BOTH boxes, they put nothing in Box B

The predictor has never been wrong in their predictions.

You have two options:
1. ONE-BOX: Take only Box B
2. TWO-BOX: Take both Box A and Box B

What would you choose and why? Please start your answer with either "ONE-BOX" or "TWO-BOX"."""


def get_available_models(client: Groq) -> List[Dict]:
    """Fetch all available text completion models from Groq."""
    models = client.models.list()
    # Filter to only include chat/text completion models
    text_models = [
        model.model_dump() for model in models.data
        if not any(excluded in model.id.lower()
                   for excluded in [
                       'whisper', # speech to text
                       'embedding',
                       'guard',  # safety / content moderation
                       'canopy'  # requires terms acceptance
                    ])
    ]
    return text_models


def query_model(client: Groq, model_name: str, prompt: str) -> Tuple[str, str]:
    """
    Query a specific model with the given prompt.

    Returns:
        Tuple of (raw_answer, final_answer)
        final_answer is either "ONE-BOX", "TWO-BOX", or "UNCLEAR"
    """
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=model_name,
            temperature=0.0,
            max_tokens=512,
        )

        raw_answer = chat_completion.choices[0].message.content.strip()

        # Extract the final answer
        final_answer = extract_answer(raw_answer)

        return raw_answer, final_answer

    except (APIError, BadRequestError, RateLimitError) as e:
        print(f"  ✗ Error querying {model_name}: {e}")
        return f"ERROR: {str(e)}", "ERROR"


def extract_answer(response: str) -> str:
    """
    Extract ONE-BOX or TWO-BOX from the model's response.

    Returns:
        "ONE-BOX", "TWO-BOX", or "UNCLEAR"
    """
    response_upper = response.upper()

    # Check first line/sentence for clear answer
    first_part = response[:200].upper()

    # Look for explicit ONE-BOX or TWO-BOX
    patterns = [
        (r'\bONE-BOX\b', "ONE-BOX"),
        (r'\bTWO-BOX(?:ES)?\b', "TWO-BOX"),
        (r'\bBOTH\s+BOX(?:ES)?\b', "TWO-BOX"),
        (r'\bONLY\s+BOX\s+B\b', "ONE-BOX"),
        (r'\bBOX\s+B\s+ONLY\b', "ONE-BOX"),
    ]

    for pattern, answer in patterns:
        if re.search(pattern, first_part):
            return answer

    # Fallback: check entire response
    one_box_count = len(re.findall(r'\bONE-BOX\b', response_upper))
    two_box_count = len(re.findall(r'\bTWO-BOX(?:ES)?\b', response_upper))

    if one_box_count > two_box_count:
        return "ONE-BOX"
    if two_box_count > one_box_count:
        return "TWO-BOX"

    return "UNCLEAR"


def save_to_csv(results: List[Dict], filename: str):
    """Save results to a CSV file."""
    fieldnames = ['model_name', 'owned_by', 'created', 'prompt',
                  'raw_answer', 'final_answer']

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✓ Results saved to {filename}")


def create_visualization(results: List[Dict],
                         output_file: str = 'newcomb_distribution.png'):
    """Create a bar chart showing the distribution of answers."""
    df = pd.DataFrame(results)

    # Filter out ERROR responses for the chart
    df_clean = df[df['final_answer'] != 'ERROR']

    if df_clean.empty:
        print("No valid responses to visualize.")
        return

    # Count the distribution
    answer_counts = df_clean['final_answer'].value_counts()

    # Create the plot
    plt.figure(figsize=(10, 6))
    colors = {'ONE-BOX': '#2ecc71', 'TWO-BOX': '#e74c3c', 'UNCLEAR': '#95a5a6'}
    bar_colors = [colors.get(answer, '#3498db') for answer in answer_counts.index]

    bars = plt.bar(
        answer_counts.index,
        answer_counts.values,
        color=bar_colors,
        edgecolor='black',
        linewidth=1.5
    )

    # Add value labels on bars
    for chart_bar in bars:
        height = chart_bar.get_height()
        plt.text(chart_bar.get_x() + chart_bar.get_width()/2., height,
                 f'{int(height)}',
                 ha='center', va='bottom', fontsize=12, fontweight='bold')

    plt.title('Newcomb\'s Problem: Distribution of Model Responses',
              fontsize=16, fontweight='bold', pad=20)
    plt.xlabel('Response', fontsize=12, fontweight='bold')
    plt.ylabel('Number of Models', fontsize=12, fontweight='bold')
    plt.grid(axis='y', alpha=0.3, linestyle='--')

    # Add total count
    total = len(df_clean)
    plt.text(0.98, 0.98, f'Total Models: {total}',
             transform=plt.gca().transAxes,
             ha='right', va='top',
             bbox={"boxstyle": 'round', "facecolor": 'wheat', "alpha": 0.5},
             fontsize=10)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Visualization saved to {output_file}")

    # Print summary statistics
    print("\n" + "="*50)
    print("SUMMARY STATISTICS")
    print("="*50)
    for answer, count in answer_counts.items():
        percentage = (count / total) * 100
        print(f"{answer:12s}: {count:3d} ({percentage:5.1f}%)")
    print("="*50)


def main():
    """Main function to run the Newcomb's problem survey."""
    parser = argparse.ArgumentParser(
        description='Survey Groq models on Newcomb\'s problem',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python newcomb_survey.py

Make sure to set your GROQ_API_KEY environment variable before running.
        """
    )
    parser.add_argument('--output', '-o', default='newcomb_results.csv',
                        help='Output CSV filename (default: newcomb_results.csv)')
    parser.add_argument('--chart', '-c', default='newcomb_distribution.png',
                        help='Output chart filename '
                             '(default: newcomb_distribution.png)')
    parser.add_argument('--models', '-m', nargs='*',
                        help='Specific models to query '
                             '(default: all available models)')
    parser.add_argument('--prompt', '-p',
                        help='Custom prompt to use (default: Newcomb\'s problem)')

    args = parser.parse_args()

    # Initialize Groq client
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("❌ GROQ_API_KEY environment variable not set.")
        return

    print("\n" + "="*50)
    print("NEWCOMB'S SURVEY")
    print("="*50)

    client = Groq(api_key=api_key)

    # Get available models
    print("\nFetching available models...")
    all_models = get_available_models(client)

    if args.models:
        # Filter to specific models
        models_to_query = [m for m in all_models if m['id'] in args.models]
        if not models_to_query:
            print(f"❌ None of the specified models found: {args.models}")
            return
    else:
        models_to_query = all_models

    print(f"Found {len(models_to_query)} model(s) to query.\n")

    # Use custom prompt if provided, otherwise use default
    prompt = args.prompt if args.prompt else NEWCOMB_PROMPT

    results = []

    # Query each model
    for i, model in enumerate(models_to_query, 1):
        model_name = model['id']
        owned_by = model.get('owned_by', 'N/A')
        created = model.get('created', 'N/A')

        print(f"[{i}/{len(models_to_query)}] Querying {model_name}...")

        raw_answer, final_answer = query_model(client, model_name, prompt)

        results.append({
            'model_name': model_name,
            'owned_by': owned_by,
            'created': created,
            'prompt': prompt,
            'raw_answer': raw_answer,
            'final_answer': final_answer
        })

        print(f"\t→ Answer: {final_answer}")

    # Save results
    save_to_csv(results, args.output)

    # Create visualization
    create_visualization(results, args.chart)

    print("\n✓ Survey complete!")


if __name__ == "__main__":
    main()
