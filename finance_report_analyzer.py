import os
import json
import webbrowser
import tempfile
import requests
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
import threading
import time
import re
import io
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import concurrent.futures
import numpy as np

# 定义目标财务指标
TARGET_INDICATORS = [
    "归母净利润", "归母净利润同比", "盈利预测", "营业总收入", "营业总收入同比", 
    "经营活动现金净流量", "投资活动现金净流量", "筹资活动现金净流量", 
    "ROE", "ROA", "销售毛利率", "销售净利率", 
    "销售费用/营业总收入", "管理费用/营业总收入", "研发费用/营业总收入", "财务费用/营业总收入",
    "应收账款/总资产", "存货/总资产", "在建工程/总资产", 
    "净资产", "负债/总资产", "重大股东变化", 
    "PE", "PB", "主营构成"
]

# 根据指标类型分类
INDICATORS_BY_TYPE = {
    "利润类指标": [
        "归母净利润", "归母净利润同比", "盈利预测", "营业总收入", "营业总收入同比", 
        "销售毛利率", "销售净利率"
    ],
    "现金流类指标": [
        "经营活动现金净流量", "投资活动现金净流量", "筹资活动现金净流量"
    ],
    "资产负债类指标": [
        "应收账款/总资产", "存货/总资产", "在建工程/总资产", "净资产", "负债/总资产"
    ],
    "收益率指标": [
        "ROE", "ROA", "销售毛利率", "销售净利率", 
        "销售费用/营业总收入", "管理费用/营业总收入", "研发费用/营业总收入", "财务费用/营业总收入"
    ],
    "股东相关信息": [
        "重大股东变化", "PE", "PB"
    ],
    "业务构成": [
        "主营构成"
    ]
}

class PDFAnalyzer:
    """PDF分析类，负责处理PDF文件并提取关键财务指标"""
    def __init__(self):
        self.pdf_cache = {}  # 缓存已下载的PDF文件

    def download_pdf(self, url):
        """下载PDF文件"""
        if url in self.pdf_cache:
            return self.pdf_cache[url]
            
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            # 将PDF内容保存到临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_file_path = temp_file.name
            
            with open(temp_file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # 缓存PDF路径
            self.pdf_cache[url] = temp_file_path
            return temp_file_path
        except Exception as e:
            print(f"下载PDF文件失败: {e}")
            return None

    def extract_text_from_pdf(self, pdf_path, page_range=None):
        """从PDF中提取文本"""
        if not pdf_path:
            return "无法加载PDF文件"
            
        text = ""
        try:
            doc = fitz.open(pdf_path)
            pages_to_process = range(len(doc)) if page_range is None else page_range
            
            for page_num in pages_to_process:
                if page_num < len(doc):
                    page = doc[page_num]
                    text += page.get_text()
            
            doc.close()
        except Exception as e:
            text = f"PDF文本提取错误: {e}"
        
        return text

    def get_pdf_cover(self, pdf_path, max_size=(800, 1000)):
        """获取PDF封面图像"""
        if not pdf_path:
            return None
            
        try:
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                return None
                
            # 获取第一页
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            
            # 将pixmap转换为PIL图像
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # 调整大小以适合显示
            img.thumbnail(max_size)
            
            # 转换为Tkinter可用的PhotoImage
            return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"PDF封面提取错误: {e}")
            return None

    def analyze_pdf_for_indicators(self, pdf_path, company_name):
        """分析PDF文件提取指标数据"""
        results = {indicator: None for indicator in TARGET_INDICATORS}
        if not pdf_path:
            return results
            
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            
            # 分阶段处理PDF内容
            # 1. 先看目录页，确定关键章节位置
            toc_text = ""
            for i in range(min(10, total_pages)):  # 前10页可能包含目录
                toc_text += doc[i].get_text()
                
            # 找到关键章节的可能页码范围
            chapter_ranges = self._find_chapter_ranges(toc_text, doc)
            
            # 2. 按章节处理不同类型的指标
            result_dict = {}
            
            # 处理资产负债表
            if "资产负债表" in chapter_ranges:
                page_range = chapter_ranges["资产负债表"]
                balance_sheet_text = ""
                for i in range(page_range[0], min(page_range[1] + 1, total_pages)):
                    balance_sheet_text += doc[i].get_text()
                
                # 提取资产负债表指标
                result_dict.update(self._extract_balance_sheet_indicators(balance_sheet_text))
            
            # 处理利润表
            if "利润表" in chapter_ranges:
                page_range = chapter_ranges["利润表"]
                income_statement_text = ""
                for i in range(page_range[0], min(page_range[1] + 1, total_pages)):
                    income_statement_text += doc[i].get_text()
                
                # 提取利润表指标
                result_dict.update(self._extract_income_statement_indicators(income_statement_text))
            
            # 处理现金流量表
            if "现金流量表" in chapter_ranges:
                page_range = chapter_ranges["现金流量表"]
                cash_flow_text = ""
                for i in range(page_range[0], min(page_range[1] + 1, total_pages)):
                    cash_flow_text += doc[i].get_text()
                
                # 提取现金流量表指标
                result_dict.update(self._extract_cash_flow_indicators(cash_flow_text))
                
            # 处理主要财务指标
            if "财务指标" in chapter_ranges:
                page_range = chapter_ranges["财务指标"]
                financial_indicators_text = ""
                for i in range(page_range[0], min(page_range[1] + 1, total_pages)):
                    financial_indicators_text += doc[i].get_text()
                
                # 提取财务指标摘要
                result_dict.update(self._extract_financial_indicators(financial_indicators_text))
                
            # 处理股东信息
            if "股东" in chapter_ranges:
                page_range = chapter_ranges["股东"]
                shareholder_text = ""
                for i in range(page_range[0], min(page_range[1] + 1, total_pages)):
                    shareholder_text += doc[i].get_text()
                
                # 提取股东信息
                result_dict.update(self._extract_shareholder_info(shareholder_text))
            
            # 如果特定章节未找到，尝试在全文搜索
            if len(result_dict) < len(TARGET_INDICATORS):
                # 分批处理文档以避免内存问题
                batch_size = 20
                for start_page in range(0, total_pages, batch_size):
                    end_page = min(start_page + batch_size, total_pages)
                    batch_text = ""
                    for i in range(start_page, end_page):
                        batch_text += doc[i].get_text()
                    
                    # 搜索未找到的指标
                    for indicator in TARGET_INDICATORS:
                        if indicator not in result_dict or not result_dict[indicator]:
                            value = self._search_indicator_in_text(indicator, batch_text)
                            if value:
                                result_dict[indicator] = value
            
            # 更新结果
            for indicator in TARGET_INDICATORS:
                if indicator in result_dict and result_dict[indicator]:
                    results[indicator] = result_dict[indicator]
            
            doc.close()
        except Exception as e:
            print(f"分析PDF文件出错: {e}")
        
        return results
    
    def _find_chapter_ranges(self, toc_text, doc):
        """查找各章节的页码范围"""
        chapter_ranges = {}
        total_pages = len(doc)
        
        # 查找目录中的关键章节
        chapter_keywords = {
            "资产负债表": ["资产负债表", "合并资产负债表"],
            "利润表": ["利润表", "合并利润表", "收益表"],
            "现金流量表": ["现金流量表", "合并现金流量表"],
            "财务指标": ["主要财务指标", "财务指标摘要", "财务会计报告"],
            "股东": ["股东", "股本变动", "股份变动", "股权结构"]
        }
        
        # 提取目录中的页码信息
        page_pattern = r'([^\d]+)\s*(\d+)'
        toc_items = re.findall(page_pattern, toc_text)
        
        chapter_pages = {}
        for title, page in toc_items:
            title = title.strip()
            try:
                page_num = int(page) - 1  # 转换为0基索引
                if page_num < 0 or page_num >= total_pages:
                    continue
                    
                # 检查是否是关键章节
                for chapter, keywords in chapter_keywords.items():
                    if any(keyword in title for keyword in keywords):
                        chapter_pages[chapter] = page_num
                        break
            except ValueError:
                continue
        
        # 确定章节范围
        sorted_chapters = sorted(chapter_pages.items(), key=lambda x: x[1])
        for i, (chapter, start_page) in enumerate(sorted_chapters):
            if i < len(sorted_chapters) - 1:
                end_page = sorted_chapters[i + 1][1] - 1
            else:
                end_page = min(start_page + 10, total_pages - 1)  # 假设章节不会太长
            
            chapter_ranges[chapter] = (start_page, end_page)
        
        # 如果目录中未找到，尝试在文档中搜索关键词
        if len(chapter_ranges) < len(chapter_keywords):
            # 每次搜索20页
            batch_size = 20
            for start_page in range(0, total_pages, batch_size):
                end_page = min(start_page + batch_size, total_pages)
                batch_text = ""
                for i in range(start_page, end_page):
                    batch_text += doc[i].get_text()
                
                # 检查每个章节关键词
                for chapter, keywords in chapter_keywords.items():
                    if chapter not in chapter_ranges:
                        for keyword in keywords:
                            if keyword in batch_text:
                                # 找到关键词，设置范围
                                chapter_ranges[chapter] = (start_page, end_page)
                                break
        
        return chapter_ranges
    
    def _extract_balance_sheet_indicators(self, text):
        """从资产负债表提取指标"""
        results = {}
        
        # 提取资产负债相关指标
        indicators_to_extract = [
            "应收账款/总资产", "存货/总资产", "在建工程/总资产", 
            "净资产", "负债/总资产"
        ]
        
        # 提取总资产
        total_assets_match = re.search(r'资产总计[^\d]*([\d,\.]+)', text)
        total_assets = None
        if total_assets_match:
            try:
                total_assets = float(total_assets_match.group(1).replace(',', ''))
            except ValueError:
                pass
        
        # 提取净资产
        net_assets_match = re.search(r'(?:净资产|所有者权益)[^\d]*([\d,\.]+)', text)
        if net_assets_match:
            try:
                results["净资产"] = float(net_assets_match.group(1).replace(',', ''))
            except ValueError:
                pass
        
        # 提取负债总额
        total_liabilities_match = re.search(r'负债总计[^\d]*([\d,\.]+)', text)
        if total_liabilities_match and total_assets:
            try:
                total_liabilities = float(total_liabilities_match.group(1).replace(',', ''))
                results["负债/总资产"] = round(total_liabilities / total_assets, 4)
            except (ValueError, ZeroDivisionError):
                pass
        
        # 提取应收账款
        accounts_receivable_match = re.search(r'应收账款[^\d]*([\d,\.]+)', text)
        if accounts_receivable_match and total_assets:
            try:
                accounts_receivable = float(accounts_receivable_match.group(1).replace(',', ''))
                results["应收账款/总资产"] = round(accounts_receivable / total_assets, 4)
            except (ValueError, ZeroDivisionError):
                pass
        
        # 提取存货
        inventory_match = re.search(r'存货[^\d]*([\d,\.]+)', text)
        if inventory_match and total_assets:
            try:
                inventory = float(inventory_match.group(1).replace(',', ''))
                results["存货/总资产"] = round(inventory / total_assets, 4)
            except (ValueError, ZeroDivisionError):
                pass
        
        # 提取在建工程
        construction_match = re.search(r'在建工程[^\d]*([\d,\.]+)', text)
        if construction_match and total_assets:
            try:
                construction = float(construction_match.group(1).replace(',', ''))
                results["在建工程/总资产"] = round(construction / total_assets, 4)
            except (ValueError, ZeroDivisionError):
                pass
        
        return results
    
    def _extract_income_statement_indicators(self, text):
        """从利润表提取指标"""
        results = {}
        
        # 提取利润相关指标
        # 归母净利润
        net_profit_match = re.search(r'(?:归属于母公司所有者的净利润|归属于母公司股东的净利润|归母净利润)[^\d]*([\d,\.]+)', text)
        if net_profit_match:
            try:
                results["归母净利润"] = float(net_profit_match.group(1).replace(',', ''))
            except ValueError:
                pass
        
        # 归母净利润同比
        yoy_match = re.search(r'(?:归属于母公司所有者的净利润|归母净利润)(?:同比|增长)(?:增长|增加|减少)?[^\d]*?([\d\.]+%)', text)
        if yoy_match:
            results["归母净利润同比"] = yoy_match.group(1)
        
        # 营业总收入
        revenue_match = re.search(r'(?:营业总收入|营业收入)[^\d]*([\d,\.]+)', text)
        if revenue_match:
            try:
                results["营业总收入"] = float(revenue_match.group(1).replace(',', ''))
            except ValueError:
                pass
        
        # 营业总收入同比
        revenue_yoy_match = re.search(r'(?:营业总收入|营业收入)(?:同比|增长)(?:增长|增加|减少)?[^\d]*?([\d\.]+%)', text)
        if revenue_yoy_match:
            results["营业总收入同比"] = revenue_yoy_match.group(1)
        
        # 销售毛利率
        gross_margin_match = re.search(r'(?:销售毛利率|毛利率)[^\d]*?([\d\.]+%)', text)
        if gross_margin_match:
            results["销售毛利率"] = gross_margin_match.group(1)
        
        # 销售净利率
        net_margin_match = re.search(r'(?:销售净利率|净利率)[^\d]*?([\d\.]+%)', text)
        if net_margin_match:
            results["销售净利率"] = net_margin_match.group(1)
        
        # 各项费用占比
        if "营业总收入" in results:
            revenue = results["营业总收入"]
            
            # 销售费用
            sales_expense_match = re.search(r'销售费用[^\d]*([\d,\.]+)', text)
            if sales_expense_match:
                try:
                    sales_expense = float(sales_expense_match.group(1).replace(',', ''))
                    results["销售费用/营业总收入"] = round(sales_expense / revenue, 4)
                except (ValueError, ZeroDivisionError):
                    pass
            
            # 管理费用
            admin_expense_match = re.search(r'管理费用[^\d]*([\d,\.]+)', text)
            if admin_expense_match:
                try:
                    admin_expense = float(admin_expense_match.group(1).replace(',', ''))
                    results["管理费用/营业总收入"] = round(admin_expense / revenue, 4)
                except (ValueError, ZeroDivisionError):
                    pass
            
            # 研发费用
            rd_expense_match = re.search(r'研发费用[^\d]*([\d,\.]+)', text)
            if rd_expense_match:
                try:
                    rd_expense = float(rd_expense_match.group(1).replace(',', ''))
                    results["研发费用/营业总收入"] = round(rd_expense / revenue, 4)
                except (ValueError, ZeroDivisionError):
                    pass
            
            # 财务费用
            finance_expense_match = re.search(r'财务费用[^\d]*([\d,\.]+)', text)
            if finance_expense_match:
                try:
                    finance_expense = float(finance_expense_match.group(1).replace(',', ''))
                    results["财务费用/营业总收入"] = round(finance_expense / revenue, 4)
                except (ValueError, ZeroDivisionError):
                    pass
        
        # 盈利预测
        forecast_match = re.search(r'(?:盈利预测|未来展望|业绩展望)[^\n]*?(\d{4})[^\n]*?(?:净利润|利润)[^\n]*?([\d\.]+亿元|\d[\d\.]*%)', text)
        if forecast_match:
            results["盈利预测"] = f"{forecast_match.group(1)}年预计{forecast_match.group(2)}"
        
        # 主营构成
        business_structure_match = re.search(r'主营业务(?:构成|分析)[^\n]*?([^。]*?(?:\d+%)[^。]*?(?:\d+%)[^。]*)', text)
        if business_structure_match:
            results["主营构成"] = business_structure_match.group(1).strip()
        
        return results
    
    def _extract_cash_flow_indicators(self, text):
        """从现金流量表提取指标"""
        results = {}
        
        # 提取现金流相关指标
        # 经营活动现金净流量
        operating_cash_match = re.search(r'经营活动(?:产生的)?现金流量净额[^\d]*([\d,\.-]+)', text)
        if operating_cash_match:
            try:
                value = operating_cash_match.group(1).replace(',', '')
                results["经营活动现金净流量"] = float(value)
            except ValueError:
                pass
        
        # 投资活动现金净流量
        investing_cash_match = re.search(r'投资活动(?:产生的)?现金流量净额[^\d]*([\d,\.-]+)', text)
        if investing_cash_match:
            try:
                value = investing_cash_match.group(1).replace(',', '')
                results["投资活动现金净流量"] = float(value)
            except ValueError:
                pass
        
        # 筹资活动现金净流量
        financing_cash_match = re.search(r'筹资活动(?:产生的)?现金流量净额[^\d]*([\d,\.-]+)', text)
        if financing_cash_match:
            try:
                value = financing_cash_match.group(1).replace(',', '')
                results["筹资活动现金净流量"] = float(value)
            except ValueError:
                pass
        
        return results
    
    def _extract_financial_indicators(self, text):
        """从财务指标摘要提取指标"""
        results = {}
        
        # 提取ROE
        roe_match = re.search(r'(?:净资产收益率|ROE)[^\d]*?([\d\.]+%)', text)
        if roe_match:
            results["ROE"] = roe_match.group(1)
        
        # 提取ROA
        roa_match = re.search(r'(?:总资产收益率|ROA)[^\d]*?([\d\.]+%)', text)
        if roa_match:
            results["ROA"] = roa_match.group(1)
        
        # PE和PB可能在财务指标或估值部分
        pe_match = re.search(r'(?:市盈率|P/E|PE)[^\d]*?([\d\.]+)', text)
        if pe_match:
            try:
                results["PE"] = float(pe_match.group(1))
            except ValueError:
                pass
        
        pb_match = re.search(r'(?:市净率|P/B|PB)[^\d]*?([\d\.]+)', text)
        if pb_match:
            try:
                results["PB"] = float(pb_match.group(1))
            except ValueError:
                pass
        
        return results
    
    def _extract_shareholder_info(self, text):
        """提取股东信息"""
        results = {}
        
        # 重大股东变化
        shareholder_change = re.search(r'(?:股东变动|主要股东变化|持股变动)[^。]*?([^。]*?(?:增持|减持|变动)[^。]*?(?:\d+%|\d+股)[^。]*)', text)
        if shareholder_change:
            results["重大股东变化"] = shareholder_change.group(1).strip()
        
        return results
    
    def _search_indicator_in_text(self, indicator, text):
        """在文本中搜索特定指标"""
        # 根据不同指标类型搜索
        if indicator == "归母净利润":
            match = re.search(r'(?:归属于母公司所有者的净利润|归属于母公司股东的净利润|归母净利润)[^\d]*([\d,\.]+)', text)
            if match:
                try:
                    return float(match.group(1).replace(',', ''))
                except ValueError:
                    pass
        
        elif indicator == "归母净利润同比":
            match = re.search(r'(?:归属于母公司所有者的净利润|归母净利润)(?:同比|增长)(?:增长|增加|减少)?[^\d]*?([\d\.]+%)', text)
            if match:
                return match.group(1)
        
        elif indicator == "营业总收入":
            match = re.search(r'(?:营业总收入|营业收入)[^\d]*([\d,\.]+)', text)
            if match:
                try:
                    return float(match.group(1).replace(',', ''))
                except ValueError:
                    pass
        
        elif indicator == "营业总收入同比":
            match = re.search(r'(?:营业总收入|营业收入)(?:同比|增长)(?:增长|增加|减少)?[^\d]*?([\d\.]+%)', text)
            if match:
                return match.group(1)
        
        # 其他指标类似处理...
        # 根据实际情况扩展此方法
        
        return None


class FinanceReportViewer:
    """财务报告查看器界面"""
    def __init__(self, root):
        self.root = root
        self.root.title("财报分析器")
        self.root.geometry("1200x800")
        
        # 数据相关
        self.stock_data = None
        self.current_company = None
        self.current_category = None
        self.pdf_analyzer = PDFAnalyzer()
        self.load_stock_data()
        
        # 创建UI界面
        self.create_ui()
    
    def load_stock_data(self):
        """加载股票数据"""
        try:
            with open('stockData.json', 'r', encoding='utf-8') as f:
                self.stock_data = json.loads(f.read())
        except Exception as e:
            messagebox.showerror("加载错误", f"无法加载股票数据: {e}")
            self.stock_data = {}
    
    def create_ui(self):
        """创建用户界面"""
        # 创建左右分隔布局
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建左侧的公司树形结构
        self.create_company_tree()
        
        # 创建右侧的信息区域
        self.create_info_area()
        
        # 设置分隔比例
        self.root.update()
        self.paned.sashpos(0, int(self.root.winfo_width()*0.3))
    
    def create_company_tree(self):
        """创建公司树形结构"""
        tree_frame = ttk.Frame(self.paned)
        self.paned.add(tree_frame, weight=1)
    
    def create_info_area(self):
        """创建右侧的信息区域"""
        info_frame = ttk.Frame(self.paned)
        self.paned.add(info_frame, weight=3)
        
        # 上下分隔
        info_paned = ttk.PanedWindow(info_frame, orient=tk.VERTICAL)
        info_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 公司信息区域
        company_frame = ttk.LabelFrame(info_paned, text="企业信息")
        info_paned.add(company_frame, weight=1)
        
        self.company_info = tk.Text(company_frame, height=5, wrap=tk.WORD, font=("Arial", 10))
        self.company_info.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 财报链接区域
        reports_frame = ttk.LabelFrame(info_paned, text="财报链接")
        info_paned.add(reports_frame, weight=1)
        
        self.reports_list = tk.Listbox(reports_frame, font=("Arial", 10))
        self.reports_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.reports_list.bind("<Double-1>", self.preview_report)
        
        # PDF预览区域
        preview_frame = ttk.LabelFrame(info_paned, text="PDF预览")
        info_paned.add(preview_frame, weight=5)
        
        preview_inner = ttk.Frame(preview_frame)
        preview_inner.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 预览控制按钮
        control_frame = ttk.Frame(preview_inner)
        control_frame.pack(fill=tk.X)
        
        ttk.Button(control_frame, text="在浏览器中打开", command=self.open_in_browser).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(control_frame, text="提取关键指标", command=self.extract_indicators).pack(side=tk.LEFT, padx=5, pady=5)
        
        # PDF预览画布
        self.canvas_frame = ttk.Frame(preview_inner)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg='#f0f0f0')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 提取结果显示区域
        results_frame = ttk.LabelFrame(info_paned, text="财务指标分析结果")
        info_paned.add(results_frame, weight=3)
        
        self.results_text = ScrolledText(results_frame, wrap=tk.WORD, font=("Arial", 10))
        self.results_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 设置分隔比例
        info_frame.update()
        # 使用 sashpos 而不是 sash_place
        info_paned.sashpos(0, int(info_frame.winfo_height()*0.1))
        info_paned.sashpos(1, int(info_frame.winfo_height()*0.2))
        info_paned.sashpos(2, int(info_frame.winfo_height()*0.7))
    
    def populate_tree(self):
        """填充树形结构"""
        if not self.stock_data:
            return
        
        # 清除旧数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 插入类别和公司
        for industry, categories in self.stock_data.items():
            industry_id = self.tree.insert('', 'end', text=industry)
            
            for category, companies in categories.items():
                category_id = self.tree.insert(industry_id, 'end', text=category)
                
                for company in companies:
                    company_name = company.get('name', '未知')
                    company_code = company.get('code', '')
                    display_name = f"{company_name} ({company_code})" if company_code else company_name
                    
                    company_id = self.tree.insert(category_id, 'end', text=display_name, values=(industry, category, company_name))
    
    def on_tree_select(self, event):
        """处理树形结构选择事件"""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_text = self.tree.item(item, 'text')
        parent = self.tree.parent(item)
        
        # 如果是公司节点
        if parent and self.tree.parent(parent):
            # 获取公司信息
            values = self.tree.item(item, 'values')
            if len(values) >= 3:
                industry, category, company_name = values
                self.current_category = category
                self.display_company_info(company_name)
        else:
            # 清除公司信息
            self.company_info.delete(1.0, tk.END)
            self.reports_list.delete(0, tk.END)
            self.canvas.delete("all")
            self.results_text.delete(1.0, tk.END)
    
    def display_company_info(self, company_name):
        """显示公司信息"""
        self.current_company = None
        
        # 在股票数据中查找公司
        for industry, categories in self.stock_data.items():
            for category, companies in categories.items():
                for company in companies:
                    if company.get('name') == company_name:
                        self.current_company = company
                        break
                if self.current_company:
                    break
            if self.current_company:
                break
        
        if not self.current_company:
            self.company_info.delete(1.0, tk.END)
            self.company_info.insert(tk.END, f"未找到{company_name}的信息")
            return
        
        # 显示公司基本信息
        self.company_info.delete(1.0, tk.END)
        self.company_info.insert(tk.END, f"公司名称: {self.current_company.get('name', '未知')}\n")
        self.company_info.insert(tk.END, f"股票代码: {self.current_company.get('code', '未知')}\n")
        self.company_info.insert(tk.END, f"所属行业: {industry}\n")
        self.company_info.insert(tk.END, f"所属类别: {category}\n")
        
        # 显示财报链接
        self.reports_list.delete(0, tk.END)
        reports = self.current_company.get('reports', {})
        
        # 按年份排序
        sorted_reports = sorted(reports.items(), key=lambda x: x[0], reverse=True)
        
        for year, url in sorted_reports:
            if url:  # 只显示有URL的年份
                self.reports_list.insert(tk.END, f"{year}年年报")
    
    def preview_report(self, event):
        """预览选中的财报"""
        selection = self.reports_list.curselection()
        if not selection or not self.current_company:
            return
        
        index = selection[0]
        year = self.reports_list.get(index).replace('年年报', '')
        
        reports = self.current_company.get('reports', {})
        url = reports.get(year)
        
        if not url:
            messagebox.showinfo("提示", "该年份没有可用的财报链接")
            return
        
        # 下载并预览PDF
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, f"正在下载 {year}年年报...\n")
        
        # 在单独的线程中下载PDF
        threading.Thread(target=self._download_and_preview_pdf, args=(url, year)).start()
    
    def _download_and_preview_pdf(self, url, year):
        """在后台线程下载PDF"""
        try:
            pdf_path = self.pdf_analyzer.download_pdf(url)
            
            if not pdf_path:
                self.root.after(0, lambda: self.results_text.insert(tk.END, f"下载失败: 无法获取PDF文件\n"))
                return
            
            # 获取PDF封面
            cover_image = self.pdf_analyzer.get_pdf_cover(pdf_path)
            
            # 在主线程中更新UI
            self.root.after(0, lambda: self._update_preview_ui(pdf_path, cover_image, url, year))
        except Exception as e:
            self.root.after(0, lambda: self.results_text.insert(tk.END, f"处理PDF时出错: {e}\n"))
    
    def _update_preview_ui(self, pdf_path, cover_image, url, year):
        """更新预览UI"""
        # 更新状态
        self.results_text.insert(tk.END, f"已下载 {year}年年报\n")
        self.results_text.insert(tk.END, f"PDF路径: {pdf_path}\n")
        
        # 清除画布
        self.canvas.delete("all")
        
        # 显示封面
        if cover_image:
            self.canvas.config(scrollregion=(0, 0, cover_image.width(), cover_image.height()))
            self.canvas.create_image(0, 0, image=cover_image, anchor=tk.NW)
            self.canvas._image = cover_image  # 保持引用以避免垃圾回收
        else:
            self.canvas.create_text(400, 300, text="无法加载PDF预览", fill="red", font=("Arial", 16))
    
    def open_in_browser(self):
        """在浏览器中打开当前PDF"""
        selection = self.reports_list.curselection()
        if not selection or not self.current_company:
            messagebox.showinfo("提示", "请先选择一个财报")
            return
            
        index = selection[0]
        year = self.reports_list.get(index).replace('年年报', '')
        
        reports = self.current_company.get('reports', {})
        url = reports.get(year)
        
        if url:
            webbrowser.open(url)
    
    def extract_indicators(self):
        """提取当前PDF的关键财务指标"""
        selection = self.reports_list.curselection()
        if not selection or not self.current_company:
            messagebox.showinfo("提示", "请先选择一个财报")
            return
        
        index = selection[0]
        year = self.reports_list.get(index).replace('年年报', '')
        
        reports = self.current_company.get('reports', {})
        url = reports.get(year)
        
        if not url:
            messagebox.showinfo("提示", "该年份没有可用的财报链接")
            return
        
        # 显示进度消息
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, f"正在分析 {self.current_company.get('name')} {year}年年报...\n")
        self.results_text.insert(tk.END, "这可能需要一些时间，请耐心等待...\n\n")
        self.root.update()
        
        # 在线程中处理
        threading.Thread(target=self._extract_indicators_thread, args=(url, year)).start()
    
    def _extract_indicators_thread(self, url, year):
        """在后台线程中提取指标"""
        try:
            # 下载PDF
            pdf_path = self.pdf_analyzer.download_pdf(url)
            
            if not pdf_path:
                self.root.after(0, lambda: self.results_text.insert(tk.END, "下载失败: 无法获取PDF文件\n"))
                return
            
            # 提取指标
            company_name = self.current_company.get('name', '未知')
            results = self.pdf_analyzer.analyze_pdf_for_indicators(pdf_path, company_name)
            
            # 在主线程更新UI
            self.root.after(0, lambda: self._update_results_ui(results, year, company_name))
        except Exception as e:
            self.root.after(0, lambda: self.results_text.insert(tk.END, f"提取指标时出错: {e}\n"))
    
    def _update_results_ui(self, results, year, company_name):
        """更新结果UI"""
        # 清空结果区域
        self.results_text.delete(1.0, tk.END)
        
        # 显示分析结果
        self.results_text.insert(tk.END, f"=== {company_name} {year}年财务指标分析结果 ===\n\n")
        
        # 按类别显示指标
        for indicator_type, indicators in INDICATORS_BY_TYPE.items():
            self.results_text.insert(tk.END, f"【{indicator_type}】\n")
            found = False
            
            for indicator in indicators:
                if indicator in results and results[indicator] is not None:
                    found = True
                    value = results[indicator]
                    # 格式化数值
                    if isinstance(value, float):
                        if abs(value) > 1000000:  # 大于100万的数值显示为亿或万
                            if abs(value) > 100000000:  # 亿
                                formatted_value = f"{value/100000000:.2f}亿"
                            else:  # 万
                                formatted_value = f"{value/10000:.2f}万"
                        else:
                            formatted_value = f"{value:,.2f}"
                    else:
                        formatted_value = str(value)
                    
                    self.results_text.insert(tk.END, f"{indicator}: {formatted_value}\n")
            
            if not found:
                self.results_text.insert(tk.END, "未找到相关指标\n")
            
            self.results_text.insert(tk.END, "\n")
        
        # 显示统计信息
        found_count = sum(1 for v in results.values() if v is not None)
        self.results_text.insert(tk.END, f"\n共找到 {found_count}/{len(TARGET_INDICATORS)} 项指标\n")


def main():
    root = tk.Tk()
    app = FinanceReportViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
