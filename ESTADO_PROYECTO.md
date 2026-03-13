# Estado del Proyecto - Moon Dev AI Agents

## Resumen
Fork del repositorio de MoonDev para trading automatizado con agentes AI.

## Configuración completada

### APIs configuradas (.env)
- **Anthropic (Claude)**: Configurado
- **DeepSeek**: Configurado (más barato, ~$0.03/backtest)

### Dependencias
- Python 3.12 instalado via Homebrew
- Virtual environment: `venv/`
- Dependencias instaladas desde `requirements_minimal.txt`

## Comandos para correr

```bash
# Activar entorno
cd ~/Desktop/personal-projects/moon-dev-ai-agents
source venv/bin/activate

# 1. Generar ideas de estrategias (test - 1 idea)
PYTHONPATH=. python src/agents/research_agent.py --test

# 2. Generar ideas en loop continuo
PYTHONPATH=. python src/agents/research_agent.py

# 3. Backtesting de ideas generadas
PYTHONPATH=. python src/agents/rbi_agent_pp_multi.py

# 4. Buscar estrategias en la web
PYTHONPATH=. python src/agents/websearch_agent.py --once

# 5. Ver ideas guardadas
cat src/data/rbi_pp_multi/ideas.txt
```

## Flujo del sistema

```
research_agent (genera ideas)
        ↓
    ideas.txt
        ↓
rbi_agent_pp_multi (backtesting)
        ↓
    backtest_stats.csv (resultados)
        ↓
trading_agent (ejecuta trades - cuando esté listo)
```

## Primera prueba exitosa
- Se generó 1 idea de estrategia usando DeepSeek
- Idea: "Trade when the 50-period MA crosses the 200-period while Chaikin Money Flow confirms with +0.2, exit on RSI reversal above 70 or below 30"

## Próximos pasos
1. Probar el backtesting (rbi_agent_pp_multi)
2. Generar más ideas
3. Analizar resultados de backtests
4. (Opcional) Crear menú interactivo
5. (Futuro) Configurar trading real con wallet

## Archivos importantes
- `.env` - API keys (NO commitear)
- `src/config.py` - Configuración de trading
- `src/data/rbi_pp_multi/ideas.txt` - Ideas generadas
- `src/data/rbi_pp_multi/backtest_stats.csv` - Resultados de backtests
- `requirements_minimal.txt` - Dependencias simplificadas

## Notas
- El `requirements.txt` original tenía conflictos, se usa `requirements_minimal.txt`
- Ollama no está instalado (modelos locales gratuitos) - opcional para después
