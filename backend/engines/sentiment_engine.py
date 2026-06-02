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
    """
    score = 50.0
    sentiment_breakdown = {"positive": 0, "negative": 0, "neutral": 0}
    flags = []

    # ── 1. News Sentiment (70% weight) ─────────────────────────
    nlp = _get_pipeline()
    if nlp and articles:
        total_score = 0
        valid_articles = 0
        
        # Process up to 10 most recent articles to keep latency low
        for idx, article in enumerate(articles[:10]):
            text = article.get("headline", "")
            if not text:
                continue
                
            try:
                res = nlp(text[:512])[0]  # Cap length for BERT
                label = res["label"]      # positive, negative, neutral
                conf = res["score"]       # 0 to 1
                
                sentiment_breakdown[label] += 1
                
                # Convert to -1 to +1 scale
                if label == "positive":
                    val = conf
                elif label == "negative":
                    val = -conf
                else:
                    val = 0
                    
                # Time decay (older articles matter slightly less)
                decay = 1.0 - (0.05 * idx)
                total_score += val * max(0.5, decay)
                valid_articles += 1
            except Exception as e:
                logger.warning(f"FinBERT error on article: {e}")
                
        if valid_articles > 0:
            avg_sentiment = total_score / valid_articles
            # Convert -1 to +1 into a 0 to 100 scale (with 50 as neutral)
            news_score = 50 + (avg_sentiment * 50)
            
            # Apply to main score
            score = (score * 0.3) + (news_score * 0.7)
            
            if news_score > 70:
                flags.append(f"Highly Positive News ({sentiment_breakdown['positive']} pos / {sentiment_breakdown['negative']} neg)")
            elif news_score < 30:
                flags.append(f"Highly Negative News ({sentiment_breakdown['negative']} neg / {sentiment_breakdown['positive']} pos)")

    else:
        flags.append("No news data available")

    # ── 2. FII / DII Flow (30% weight) ─────────────────────────
    if fii_dii:
        fii_net = fii_dii.get("fii_net", 0)
        dii_net = fii_dii.get("dii_net", 0)
        
        net_inst_flow = fii_net + dii_net
        
        if fii_net > 1000:
            score += 15
            flags.append(f"Strong FII Buying (+₹{fii_net}Cr)")
        elif fii_net > 0:
            score += 5
        elif fii_net < -1000:
            score -= 15
            flags.append(f"Strong FII Selling (₹{fii_net}Cr)")
        elif fii_net < 0:
            score -= 5
            
        if dii_net > 1000 and fii_net < 0:
            flags.append(f"DIIs absorbing FII selling (+₹{dii_net}Cr)")
            score += 5  # DII support
            
    else:
        flags.append("No institutional flow data")

    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 2),
        "flags": flags,
        "news_breakdown": sentiment_breakdown
    }
