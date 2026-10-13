"""
ATBot — Sentiment Analysis Engine
Uses FinBERT (HuggingFace) to analyze news headlines and combine 
with FII/DII flow to generate a sentiment score (0-100).
"""

import logging
import pandas as pd
from transformers import pipeline

logger = logging.getLogger(__name__)

# Initialize pipeline lazily to save memory
_finbert_pipeline = None

def _get_pipeline():
    global _finbert_pipeline
    if _finbert_pipeline is None:
        logger.info("Loading FinBERT pipeline (this may take a moment on first run)...")
        try:
            # Note: For production on small VPS, you might want to switch to a quantized model
            _finbert_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
        except Exception as e:
            logger.error(f"Failed to load FinBERT: {e}")
    return _finbert_pipeline


def analyze_sentiment(articles: list[dict], fii_dii: dict = None) -> dict:
    """
    Generate Sentiment Score (0-100).
    Input: list of article dicts (must have "headline"), and optionally FII/DII dict.
    Returns None if no articles are found to avoid defaulting to 50.
    """
    if not articles:
        return {
            "score": None,
            "flags": ["No news data available"],
            "news_breakdown": {"positive": 0, "negative": 0, "neutral": 0}
        }

    score = 50.0
    sentiment_breakdown = {"positive": 0, "negative": 0, "neutral": 0}
    flags = []

    # --- 1. News Sentiment (70% weight) ---
    nlp = _get_pipeline()
    if nlp:
        total_score = 0
        valid_articles = 0
        
        for idx, article in enumerate(articles[:10]):
            headline = article.get("headline", "")
            summary = article.get("summary", "")
            text = f"{headline}. {summary}".strip(" .")
            if not text: continue
                
            try:
                res = nlp(text[:512])[0]
                label = res["label"]
                conf = res["score"]
                sentiment_breakdown[label] += 1
                
                if label == "positive": val = conf
                elif label == "negative": val = -conf
                else: val = 0
                    
                decay = 1.0 - (0.05 * idx)
                total_score += val * max(0.5, decay)
                valid_articles += 1
            except Exception as e:
                logger.warning(f"FinBERT error: {e}")
                
        if valid_articles > 0:
            avg_sentiment = total_score / valid_articles
            news_score = 50 + (avg_sentiment * 50)
            score = (score * 0.3) + (news_score * 0.7)
            
            if news_score > 70:
                flags.append(f"Highly Positive News ({sentiment_breakdown['positive']} pos / {sentiment_breakdown['negative']} neg)")
            elif news_score < 30:
                flags.append(f"Highly Negative News ({sentiment_breakdown['negative']} neg / {sentiment_breakdown['positive']} pos)")

    # --- 2. FII / DII Flow (30% weight: Max +/-15 pts) ---
    if fii_dii:
        fii_net = float(fii_dii.get("fii_net") or 0)
        dii_net = float(fii_dii.get("dii_net") or 0)
        flow_score = 0.0

        # Scenario A: Both Institutional Giants Aligned Strongly
        if fii_net >= 1000 and dii_net >= 1000:
            flow_score += 15.0
            flags.append(f"FIIs and DIIs buying both ({fii_net + dii_net:+.0f}Cr)")
        elif fii_net <= -1000 and dii_net <= -1000:
            flow_score -= 15.0
            flags.append(f"FIIs and DIIs selling both ({fii_net + dii_net:+.0f}Cr)")
        else:
            # 1. FII Flow (Max +/-10)
            if fii_net >= 1000:
                flow_score += 10.0
                flags.append(f"Strong FII Buying (+{fii_net:.0f}Cr)")
            elif fii_net > 0:
                flow_score += 4.0
                flags.append(f"Mild FII Buying (+{fii_net:.0f}Cr)")
            elif fii_net <= -1000:
                flow_score -= 10.0
                flags.append(f"Strong FII Selling ({fii_net:.0f}Cr)")
            elif fii_net < 0:
                flow_score -= 4.0
                flags.append(f"Mild FII Selling ({fii_net:.0f}Cr)")

            # 2. DII Flow (Max +/-5)
            if dii_net >= 1000:
                flow_score += 5.0
                flags.append(f"Strong DII Buying (+{dii_net:.0f}Cr)")
            elif dii_net > 0:
                flow_score += 2.0
            elif dii_net <= -1000:
                flow_score -= 5.0
                flags.append(f"Strong DII Selling ({dii_net:.0f}Cr)")
            elif dii_net < 0:
                flow_score -= 2.0

            # 3. Cross-Flow Dynamics & Absorption
            if dii_net >= 1000 and fii_net < 0:
                flags.append(f"DIIs absorbing FII selling (+{dii_net:.0f}Cr)")
                flow_score += 4.0
            elif fii_net >= 1000 and dii_net < 0:
                flags.append(f"FIIs absorbing DII selling (+{fii_net:.0f}Cr)")

        if fii_net == 0 and dii_net == 0:
            flags.append("Neutral institutional flow")

        # Bound strictly within the 30% weight budget (+/-15 points)
        score += max(-15.0, min(15.0, flow_score))
    else:
        flags.append("No institutional flow data")

    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 2),
        "flags": flags,
        "news_breakdown": sentiment_breakdown
    }
