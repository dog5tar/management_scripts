import os
import pandas as pd
from pathlib import Path
from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer

def main():
    file_path = input("📄 Enter the full path to the CSV file: ").strip()
    path = Path(file_path)

    if not path.is_file():
        print("❌ Invalid file path.")
        return

    # Load CSV
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"❌ Failed to read CSV: {e}")
        return

    print(f"📋 Available columns: {', '.join(df.columns)}")
    col = input("🔑 Enter the column name that contains the keyword phrases: ").strip()

    if col not in df.columns:
        print("❌ Specified column not found.")
        return

    # Clean keyword phrases
    df[col] = df[col].astype(str).str.strip().str.lower()
    df = df[df[col].str.len() > 2]
    df = df[df[col].str.contains(r'[a-zA-Z]', regex=True)]
    df = df.drop_duplicates(subset=[col])
    docs = df[col].tolist()

    if not docs:
        print("⚠️ No valid phrases found.")
        return

    # Train BERTopic model
    print("🔄 Clustering and naming topics with BERTopic...")
    vectorizer_model = CountVectorizer(ngram_range=(1, 3), stop_words="english")
    topic_model = BERTopic(vectorizer_model=vectorizer_model, verbose=True)
    topics, _ = topic_model.fit_transform(docs)

    df['Cluster'] = [topic_model.get_topic_info().loc[topic_model.get_topic_info()['Topic'] == topic, 'Name'].values[0] if topic != -1 else "Miscellaneous" for topic in topics]

    # Group by cluster name
    grouped = df.groupby('Cluster')[col].apply(lambda phrases: ', '.join(phrases)).reset_index()
    grouped.columns = ['Cluster', 'Keywords']

    # Save
    output_path = path.parent / "keyword-clusters.csv"
    grouped.to_csv(output_path, index=False)
    print(f"✅ Clustered + named keywords saved to: {output_path}")

if __name__ == "__main__":
    main()
