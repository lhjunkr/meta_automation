import base64

# pygooglenews still imports feedparser 5.x, which expects this Python 2-era alias.
# Define it before pygooglenews imports feedparser so GitHub Actions can run on Python 3.11.
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes

from config import is_dry_run
from content import (
    match_selected_articles,
    select_best_articles,
)
from news import fetch_top_news
from outputs import (
    create_run_dir,
    save_selected_articles,
    save_selected_news,
)
from pipeline import (
    handle_publish_success,
    process_content_pipeline,
    retry_failed_categories_with_backup,
)
from publishing import publish_to_social_channels

# Main. 전체 콘텐츠 생성 파이프라인을 실행합니다.
if __name__ == "__main__":
    # 실행 폴더를 만든 뒤 오늘 사용할 뉴스 후보를 수집합니다.
    run_dir = create_run_dir()
    news_list = fetch_top_news()

    for news in news_list[:3]:
        print(news)

    print(f"\n필터링 완료. 총 {len(news_list)}개의 신선한 뉴스를 확보했습니다.\n")

    if len(news_list) > 0:
        print("--- [Gemini 선정 결과] ---")
        selected_result = select_best_articles(news_list)
        print(selected_result)

        with open(run_dir / "gemini_selected_result.txt", "w", encoding="utf-8") as f:
            f.write(selected_result)

        # Gemini가 고른 ID를 원본 기사 데이터와 매칭한 뒤 콘텐츠 생성 파이프라인을 실행합니다.
        selected_articles = match_selected_articles(selected_result, news_list)

        selected_articles = process_content_pipeline(selected_articles, run_dir)
        selected_articles = retry_failed_categories_with_backup(selected_articles, run_dir)

        # 최종 산출물을 파일로 저장합니다.
        save_selected_news(selected_articles, run_dir)
        save_selected_articles(selected_articles, run_dir)

        if is_dry_run():
            print("[DRY_RUN] 실제 인스타그램/페이스북 업로드를 건너뜁니다.")
            published_articles = []
        else:
            published_articles = publish_to_social_channels(selected_articles)
            handle_publish_success(published_articles)


        print("\n[완료] 오늘 콘텐츠 생성 파이프라인이 끝났습니다.")
        print(f"산출물 저장 위치: {run_dir}")

    else:
        print("수집된 뉴스가 없습니다. 구글 뉴스 연결 상태를 확인하세요.")
