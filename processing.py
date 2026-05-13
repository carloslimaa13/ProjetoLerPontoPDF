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

    @staticmethod
    def _time_to_minutes(time_str: str) -> int:
        if not time_str or time_str == "00:00": return 0
        match = re.search(r"(\d{2,3}):(\d{2})", str(time_str))
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
        return 0

    @staticmethod
    def _minutes_to_time(minutes: int) -> str:
        h = int(minutes // 60)
        m = int(minutes % 60)
        return f"{h:02d}:{m:02d}"

    def _extract_info(self, page) -> dict:
        texto = page.get_text("text")
        if not texto: return None

        linhas = [l.strip() for l in texto.split('\n') if l.strip()]
        nome = None
        departamento = "Desconhecido"
        faltas = None
        extras = None

        for i, linha in enumerate(linhas):
            if "Departamento:" in linha and departamento == "Desconhecido":
                match = re.search(r"Departamento:\s*([^.]+)", linha, re.IGNORECASE)
                if match: departamento = match.group(1).strip()

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

            if "TOTAIS" in linha and faltas is None:
                tempos = []
                for j in range(i, min(i + 15, len(linhas))):
                    cand_tempo = linhas[j].strip()
                    if re.match(r"^\d{2,3}:\d{2}$", cand_tempo): tempos.append(cand_tempo)
                if len(tempos) >= 3:
                    faltas, extras = tempos[1], tempos[2]
                else:
                    faltas, extras = "00:00", "00:00"

            if nome and departamento != "Desconhecido" and faltas is not None: break
                
        if nome:
            return {"Colaborador": nome, "Departamento": departamento, "Faltas_Raw": faltas if faltas else "00:00", "Extras_Raw": extras if extras else "00:00"}
        return None

    def execute_pipeline(self) -> pl.DataFrame:
        dados_agrupados = {}
        for caminho in self.file_paths:
            try:
                with fitz.open(caminho) as pdf:
                    for page in pdf:
                        info = self._extract_info(page)
                        if info:
                            chave = (info["Colaborador"], info["Departamento"])
                            if chave not in dados_agrupados: dados_agrupados[chave] = {"faltas": 0, "extras": 0}
                            dados_agrupados[chave]["faltas"] += self._time_to_minutes(info["Faltas_Raw"])
                            dados_agrupados[chave]["extras"] += self._time_to_minutes(info["Extras_Raw"])
            except Exception as e:
                logging.error(f"Erro em execute_pipeline: {e}")

        dados_finais = [{"Colaborador": n, "Departamento": d, "Faltas (HH:MM)": self._minutes_to_time(t["faltas"]), "Extras (HH:MM)": self._minutes_to_time(t["extras"])} for (n, d), t in dados_agrupados.items()]
        df = pl.DataFrame(dados_finais)
        return df.sort("Faltas (HH:MM)", descending=True) if not df.is_empty() else df

    def extract_all_dates(self) -> pl.DataFrame:
        datas = set()
        padrao = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
        for c in self.file_paths:
            try:
                with fitz.open(c) as pdf:
                    for page in pdf: datas.update(padrao.findall(page.get_text("text")))
            except: pass
        return pl.DataFrame({"Datas Encontradas": sorted(list(datas), key=lambda x: (x[6:], x[3:5], x[:2]))})

    # --- ATUALIZADO: EXTRAÇÃO DIÁRIA DE FALTAS E EXTRAS ---
    def extract_daily_faults(self) -> pl.DataFrame:
        dados_diarios = []
        for caminho in self.file_paths:
            try:
                with fitz.open(caminho) as pdf:
                    for page in pdf:
                        texto = page.get_text("text")
                        blocos = re.split(r"(\b\d{2}/\d{2}/\d{4}\b)", texto)
                        data_atual = None
                        
                        for parte in blocos:
                            if re.match(r"^\d{2}/\d{2}/\d{4}$", parte):
                                data_atual = parte
                            elif data_atual:
                                if "SÁB" in parte.upper() or "DOM" in parte.upper() or "FOLGA" in parte.upper():
                                    data_atual = None
                                    continue
                                    
                                tempos = re.findall(r"\b\d{2,3}:\d{2}\b", parte)
                                min_falta = 0
                                min_extra = 0
                                
                                # Lógica Matemática Secullum
                                if len(tempos) == 1:
                                    if self._time_to_minutes(tempos[0]) >= 480:
                                        min_falta = self._time_to_minutes(tempos[0])
                                elif len(tempos) == 6:
                                    # [4] são as horas normais. Se < 8h, a sexta marcação é débito (Falta)
                                    if self._time_to_minutes(tempos[4]) < 480:
                                        min_falta = self._time_to_minutes(tempos[5])
                                    # Se a pessoa fez 8h cravadas, a sexta marcação é crédito (Extra)
                                    else:
                                        min_extra = self._time_to_minutes(tempos[5])
                                elif len(tempos) >= 7:
                                    # Fez horas normais, teve atraso E fez extra no mesmo dia!
                                    min_falta = self._time_to_minutes(tempos[5])
                                    min_extra = self._time_to_minutes(tempos[6])
                                    
                                dados_diarios.append({
                                    "Data": data_atual,
                                    "Minutos_Falta": min_falta,
                                    "Minutos_Extra": min_extra
                                })
                                data_atual = None
            except Exception as e:
                logging.error(f"Erro na extração diária: {e}")
                
        return pl.DataFrame(dados_diarios)