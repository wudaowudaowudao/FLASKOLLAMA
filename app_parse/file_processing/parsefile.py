


import os
import shutil
#import faiss
import json

from exceptiongroup import catch

from app_parse.file_processing.FaissCreate import FaissCreate
from app_parse.file_processing.translate_v2 import MarkdownTranslator

#os.environ["CUDA_VISIBLE_DEVICES"] = "0"

from magic_pdf.data.read_api import read_local_office,read_local_images
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.data.data_reader_writer import FileBasedDataWriter,FileBasedDataReader
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.config.enums import SupportedPdfParseMethod

import torch
#from chat_backend.settings import PARSE_FILE_SETTINGS
from config import Config
from .titleAnalysis_v4 import TitleAnalyzer

class ParseFile:
    def __init__(self, isWatermark = False, isoutpu = False):
        
        self.isWatermark = isWatermark
        self.isWatermark = isWatermark
        self.isoutpu = isoutpu
        self.langs = ['ch_sim', 'en', 'ru']
        self.FILE_PATH = Config.PARSE_FILE_SETTINGS['FILE_PATH']
        if not os.path.exists(self.FILE_PATH):
            os.makedirs(self.FILE_PATH)
        self.DB_PATH = Config.PARSE_FILE_SETTINGS['DB_PATH']
        if not os.path.exists(self.DB_PATH):
            os.makedirs(self.DB_PATH)
        self.PARSE_DATA_PATH = Config.PARSE_FILE_SETTINGS['PARSE_DATA_PATH']
        if not os.path.exists(self.PARSE_DATA_PATH):
            os.makedirs(self.PARSE_DATA_PATH)

        #self.pdf = PdfParser()
        #print('PDF IS Connected')

        self.faiss = FaissCreate()
        #print('Faiss IS Connected')

        #self.graph = MarkdownToNeo4j()
        #print('neo4j is connected')

        self.reader1 = FileBasedDataReader("")
        print('FileBasedDataReader is connected')

        self.translator = MarkdownTranslator()
        print('translator is connected')
 

    def set_parse_param(self,fileLanguage,wordsRecInterface,fileSet,file_name):
        self.fileLanguage = fileLanguage
        self.wordsRecInterface = wordsRecInterface
        self.fileSet = fileSet
        self.file_name = file_name
        #self.pdf.set_parse_param(self.index,self.ocrAPI)
        #self.blocker = BlockerByTitle(self.index, self.ocrAPI,self.pdf)


    def check_file_type(self,file_path):
        ext = os.path.splitext(file_path)[1].lower()
        
        image_ext = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        office_ext = ['.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx']
        if ext in image_ext:
            return 'image'
        elif ext == '.pdf':
            return 'pdf'
        elif ext in office_ext:
            return 'office'
        else:
            return 'unknown'
        
    def set_writer(self, file_id):
        self.file_id = file_id
        local_image_dir = f"{self.PARSE_DATA_PATH}/{file_id}/image"
        local_md_dir = f"{self.PARSE_DATA_PATH}/{file_id}"
        self.image_writer, self.md_writer = FileBasedDataWriter(local_image_dir), FileBasedDataWriter(
        local_md_dir
    )



    def classify_file(self, filefullpath):
        """
            根据文件类型进行分类
        """
        pipe_result = None

        try:
            file_type = self.check_file_type(filefullpath)
            if file_type == "pdf":
                pipe_result = self.work_pdf(filefullpath)
            elif file_type == "image":
                pipe_result = self.work_image(filefullpath)
            elif file_type == "office":
                pipe_result = self.work_office(filefullpath)
        except Exception as e:
            print(f"classify_file:{e}")
            return pipe_result
        
        
        return pipe_result 
        
    def work_pdf(self, filefullpath):
        filemold = self.wordsRecInterface

        # read bytes        
        pdf_bytes = self.reader1.read(filefullpath)  # read the pdf content

        # proc
        ##
        # Create Dataset Instance
        ds = PymuDocDataset(pdf_bytes)

        print(f"{filefullpath}:PymuDocDataset")
        ## inference
        #if ds.classify() == SupportedPdfParseMethod.OCR:
        infer_result = ds.apply(doc_analyze, ocr=True, mold=filemold)

        print(f"{filefullpath}:doc_analyze")
        ## pipeline
        pipe_result = infer_result.pipe_ocr_mode(self.image_writer)





        #else:
        #infer_result = ds.apply(doc_analyze, ocr=False)

            ## pipeline
            #pipe_result = infer_result.pipe_txt_mode(self.image_writer)
        
        return pipe_result
    


    def work_image(self, filefullpath):
        ds = read_local_images(filefullpath)[0]
        infer_result = ds.apply(doc_analyze, ocr=True)

        ## pipeline
        pipe_result = infer_result.pipe_ocr_mode(self.image_writer)
        
        return pipe_result

    def work_office(self, filefullpath):
        ds = read_local_office(filefullpath)[0]
        infer_result = ds.apply(doc_analyze, ocr=False)

        ## pipeline
        pipe_result = infer_result.pipe_txt_mode(self.image_writer)
       
        return pipe_result

    def dump_json(self, pipe_result,image_dir,translate="false"):
        try:

            md_content = pipe_result.get_markdown(image_dir)

            pipe_result.dump_md(self.md_writer, f"{self.file_id}.md", image_dir)

            ### get content list content
            content_list_content = pipe_result.get_content_list(image_dir)
            ### dump content list
            pipe_result.dump_content_list(self.md_writer, f"{self.file_id}_content_list.json", image_dir)

            titleAnalyzer = TitleAnalyzer("")

            content_list = f"{self.PARSE_DATA_PATH}/{self.file_id}/{self.file_id}_content_list.json"
            # titleAnalyzer.copy_file(content_list)
            titleAnalyzer.process_file(content_list)


            with open(content_list, 'r', encoding='utf-8') as f:
                content = f.read()
                data = json.loads(content)

                merge_data = self.process_adjacent_nodes(data)

                if translate == "true":
                    merge_data = self.translator.translate_json(merge_data)

                with open(content_list,'w',encoding='utf-8') as fw:
                    json.dump(merge_data, fw, ensure_ascii=False, indent=4)

            ### get middle json
            middle_json_content = pipe_result.get_middle_json()

            ### dump middle json
            pipe_result.dump_middle_json(self.md_writer, f'{self.file_id}_middle.json')

            pipe_result.draw_layout(f'{self.PARSE_DATA_PATH}/{self.file_id}/{self.file_id}_layout.pdf')

            #self.graph.import_markdown(f"{image_dir}/md/{self.file_id}.md",self.fileSet,self.file_name,self.file_id)

        except Exception as e:
            print(f"dump_json:{e}")

        # 封装处理相邻节点的代码为函
    def process_adjacent_nodes(self, data):
        new_data = []
        index = 0
        while index < len(data):
            if data[index]['type'] == 'text' and 'text_level' not in data[index]:
                merged_text = data[index]['text']
                page_idx = data[index]['page_idx']
                while index + 1 < len(data) and data[index + 1]['type'] == 'text' and 'text_level' not in data[
                    index + 1] and data[index + 1]['page_idx'] == page_idx:
                    index += 1
                    merged_text += '\n' + data[index]['text']
                new_data.append({
                    'type': 'text',
                    'text': merged_text,
                    'page_idx': page_idx
                })
            else:
                new_data.append(data[index])
            index += 1
        return new_data

    def Parse_work(self, filefullpath,file_data,filename,toFile=True,faiss_path=""):

        file_id = file_data   #['fileId']
        self.set_writer(file_id)

        if os.path.exists(filefullpath):
            try:
                pipe_result = self.classify_file(filefullpath)

                if self.fileLanguage == "ch":
                    bTrans = "false"
                else:
                    bTrans = "true"
                self.dump_json(pipe_result, f"{self.PARSE_DATA_PATH}/{file_id}",bTrans)

            except Exception as e:
                print(f"Parse_work:{e}")

            print("==================="+ str(pipe_result))
            try:
                #faiss_path = f"{self.PARSE_DATA_PATH}\\{file_id}"
                if toFile:
                    if faiss_path == "":
                        faiss_path = os.path.join(Config.PARSE_FILE_SETTINGS['BASE_FAISS_SAVE_FOLDER'], file_id)
                    print(f"{faiss_path}:faiss_save_folder")
                    json_path = f"{self.PARSE_DATA_PATH}/{self.file_id}/{self.file_id}_content_list.json"
                    self.faiss.set_json_faiss(file_id,json_path, faiss_path,filename)
                return ""
            except Exception as e:
                print(torch.cuda.memory_summary())
                return f"错误: {self.file_name}: - {str(e)}"

