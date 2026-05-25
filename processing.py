import fitz  # PyMuPDF
import polars as pl
import re
import logging
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class PontoProcessor:
    def __init__(self, file_paths: List[str]):
        if isinstance(file_paths, str):
            self.file_paths = [file_paths]
        else:
            self.file_paths = file_paths

    def _get_x_cols(self, pdf) -> tuple:
        for page in pdf:
            words = page.get_text("words")
            y_totais = None
            for w in words:
                if "TOTAIS" in w[4].upper():
                    y_totais = (w[1] + w[3]) / 2
                    break
            
            if y_totais is not None:
                tempos = []
                for w in words:
                    txt = re.sub(r'[*^]', '', w[4].strip())
                    if re.match(r"^\d{2,3}:\d{2}$", txt):
                        y_word = (w[1] + w[3]) / 2
                        if abs(y_word - y_totais) < 10:
                            tempos.append(((w[0] + w[2]) / 2, txt))
                
                if tempos:
                    tempos.sort(key=lambda x: x[0])
                    x_normais = tempos[0][0] if len(tempos) > 0 else None
                    x_faltas = tempos[1][0] if len(tempos) > 1 else None
                    x_extras = tempos[2][0] if len(tempos) > 2 else None
                    return x_normais, x_faltas, x_extras 
        return None, None, None

    def _extract_page_info(self, page, x_normais, x_faltas, x_extras) -> dict:
        texto = page.get_text("text")
        if not texto: return None

        linhas = [l.strip() for l in texto.split('\n') if l.strip()]
        nome = None
        departamento = "Desconhecido"

        for i, linha in enumerate(linhas):
            if "Departamento:" in linha and departamento == "Desconhecido":
                match = re.search(r"Departamento:\s*([^.]+)", linha, re.IGNORECASE)
                if match:
                    departamento = match.group(1).strip()

            if "NOME:" in linha and not nome:
                cand_mesma_linha = linha.replace("NOME:", "").strip()
                if cand_mesma_linha:
                    nome = re.sub(r'\s+\d+$', '', cand_mesma_linha).strip()
                else:
                    for j in range(i + 1, min(i + 15, len(linhas))):
                        cand = linhas[j]
                        if ":" in cand: continue
                        if cand.lower() == "isento": continue
                        if "HORÁRIO DE TRABALHO" in cand.upper(): continue
                        if cand.isdigit(): continue
                        if re.match(r"^\d{2}\.\d{3}\.\d{3}/", cand): continue
                        nome = re.sub(r'\s+\d+$', '', cand).strip()
                        break

            if nome and departamento != "Desconhecido":
                break

        registros_diarios = {} 
        words = page.get_text("words") 
        dates_info = []

        for w in words:
            match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", w[4])
            if match:
                x_center = (w[0] + w[2]) / 2
                y_center = (w[1] + w[3]) / 2
                dates_info.append((x_center, y_center, match.group(1)))

        if dates_info:
            grupos_x = []
            for x, y, dt in dates_info:
                alocado = False
                for g in grupos_x:
                    if abs(g['x_ref'] - x) < 30:
                        g['elementos'].append((y, dt))
                        alocado = True
                        break
                if not alocado:
                    grupos_x.append({'x_ref': x, 'elementos': [(y, dt)]})

            maior_grupo = max(grupos_x, key=lambda g: len(g['elementos']))
            elementos_datas = maior_grupo['elementos'] 

            if x_normais is not None or x_faltas is not None or x_extras is not None:
                for y_data, dt in elementos_datas:
                    hora_encontrada = "00:00" 
                    falta_encontrada = "00:00"
                    extra_encontrada = "00:00"
                    
                    for w in words:
                        txt = re.sub(r'[*^]', '', w[4].strip())
                        if re.match(r"^\d{2,3}:\d{2}$", txt):
                            y_word = (w[1] + w[3]) / 2
                            x_word = (w[0] + w[2]) / 2
                            if abs(y_word - y_data) < 10:
                                if x_normais and abs(x_word - x_normais) < 20:
                                    hora_encontrada = txt
                                elif x_faltas and abs(x_word - x_faltas) < 20:
                                    falta_encontrada = txt
                                elif x_extras and abs(x_word - x_extras) < 20:
                                    extra_encontrada = txt
                    
                    registros_diarios[dt] = {
                        "normais": hora_encontrada,
                        "faltas": falta_encontrada,
                        "extras": extra_encontrada
                    }

        if nome:
            return {
                "Colaborador": nome,
                "Departamento": departamento,
                "Registros": registros_diarios
            }
        return None

    def execute_pipeline(self) -> pl.DataFrame:
        dados_globais = {} 

        for caminho in self.file_paths:
            try:
                with fitz.open(caminho) as pdf:
                    x_normais, x_faltas, x_extras = self._get_x_cols(pdf)
                    
                    for page in pdf:
                        info = self._extract_page_info(page, x_normais, x_faltas, x_extras)
                        if info:
                            chave = info["Colaborador"]
                            
                            if chave not in dados_globais:
                                dados_globais[chave] = {
                                    "Colaborador": info["Colaborador"],
                                    "Departamento": info["Departamento"],
                                    "Registros": info["Registros"]
                                }
                            else:
                                dados_globais[chave]["Registros"].update(info["Registros"])
            except Exception as e:
                logging.error(f"Erro em execute_pipeline: {e}")

        dados_finais = []
        for chave, valores in dados_globais.items():
            for dt, regs in valores["Registros"].items():
                dados_finais.append({
                    "Colaborador": valores["Colaborador"],
                    "Departamento": valores["Departamento"],
                    "Data": dt,
                    "Normais": regs["normais"], # <--- Alterado o nome de string de saída aqui
                    "Faltas": regs["faltas"],
                    "Extras": regs["extras"]
                })

        df = pl.DataFrame(dados_finais)
        return df.sort(["Colaborador", "Data"]) if not df.is_empty() else df
