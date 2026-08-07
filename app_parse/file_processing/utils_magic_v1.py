# 优化并封装成类
import os
import fitz
import cv2
import numpy as np
from datetime import datetime
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from app.file_processing.rm_watermark import remove_watermark_from_ndarray


class PDFProcessor:
    def __init__(self, pdf_path: str, save_dir: str = ".", dpi: int = 200):
        self.pdf_path = pdf_path
        self.dpi = dpi
        self.save_dir = save_dir
        self.pdf_file_name = os.path.splitext(os.path.basename(pdf_path))[0]
        self.date_str = datetime.now().strftime("%Y%m%d")
        self.output_dir = os.path.join(self.save_dir, f"images_{self.date_str}", self.pdf_file_name)
        os.makedirs(self.output_dir, exist_ok=True)

    def _fitz_page_to_image(self, page, page_number=None, post_process_func=None):
        logger.info(f"Converting page {page_number} to image...")
        try:
            mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
            pm = page.get_pixmap(matrix=mat, alpha=False)

            if pm.width > 4500 or pm.height > 4500:
                scale = min(4500 / pm.width, 4500 / pm.height, 1.0)
                mat = fitz.Matrix(scale, scale)
                pm = page.get_pixmap(matrix=mat, alpha=False)

            img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, 3)
            img = remove_watermark_from_ndarray(img)

            if post_process_func:
                img = post_process_func(img)

            save_path = os.path.join(self.output_dir, f"page_{page_number}.png")
            cv2.imwrite(save_path, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            logger.info(f"Saved processed image to {save_path}")

            return {"img": img, "width": pm.width, "height": pm.height}
        except Exception as e:
            logger.error(f"Error processing page {page_number}: {e}")
            return {"img": [], "width": 0, "height": 0}

    def process_single_thread(self):
        logger.info("Processing PDF using single thread...")
        results = []
        with fitz.open(self.pdf_path) as doc:
            for page_num in range(len(doc)):
                results.append(self._fitz_page_to_image(doc[page_num], page_num))
        return results

    def process_with_threads(self, num_threads=4):
        logger.info("Processing PDF using thread pool...")
        with fitz.open(self.pdf_path) as doc:
            num_pages = len(doc)
            results = [None] * num_pages

            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = {
                    executor.submit(self._fitz_page_to_image, doc[page_num], page_num): page_num
                    for page_num in range(num_pages)
                }
                for future in as_completed(futures):
                    page_num = futures[future]
                    try:
                        results[page_num] = future.result()
                    except Exception as e:
                        logger.error(f"Failed to process page {page_num} in thread pool: {e}")
        return results

    def process_with_processes(self, num_workers=4):
        logger.info("Processing PDF using process pool...")
        with fitz.open(self.pdf_path) as doc:
            pdf_bytes_list = []
            for i in range(doc.page_count):
                sub_doc = fitz.open()
                sub_doc.insert_pdf(doc, from_page=i, to_page=i)
                pdf_bytes_list.append((sub_doc.tobytes(), i))

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            results = list(executor.map(self._convert_page_bytes_wrapper, pdf_bytes_list))
        return results

    def _convert_page_bytes_wrapper(self, args):
        bytes_page, page_number = args
        try:
            with fitz.open("pdf", bytes_page) as pdf:
                page = pdf[0]
                return self._fitz_page_to_image(page, page_number)
        except Exception as e:
            logger.error(f"Process error on page {page_number}: {e}")
            return {"img": [], "width": 0, "height": 0}


if __name__ == '__main__':
    pdf_path = '../../data/TB2.pdf'
    processor = PDFProcessor(pdf_path, save_dir="./output")

    # 任选一种：
    results = processor.process_with_processes(num_workers=4)
    # results = processor.process_with_threads(num_threads=4)
    # results = processor.process_single_thread()

    print("Processing complete. Total pages:", len(results))
