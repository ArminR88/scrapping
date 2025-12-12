# Python Scraping Project

This project contains tools and scripts for web scraping, with a focus on comparing different libraries to select the best tool for the job.

## Performance Benchmark: Playwright vs. Selenium

The script `comparison_selenium_playwright.py` provides a direct performance comparison between Playwright and Selenium. It runs a series of automated scraping tasks with both libraries and measures the time taken, including browser startup and element location.

### Conclusion

Based on the benchmark results, **Playwright** was selected as the primary tool for the main crawling implementation in this project. It consistently demonstrated faster execution times and a more stable, modern API.

### How to Run the Benchmark

The comparison can be run inside the containerized environment to ensure consistent results.

1.  **Build the container image:**
    ```bash
    podman build -t scrapping .
    ```

2.  **Run the benchmark script:**
    ```bash
    podman run --rm -it --shm-size=1g scrapping
    ```
    This command executes `comparison_selenium_playwright.py` and will output a summary table comparing the performance metrics (mean, median, stdev) for both tools.

## Main Crawler

The main scraping logic will be built using Playwright.

*(Placeholder: Instructions for running the main crawler will be added here once it is developed.)*