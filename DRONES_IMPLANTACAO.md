# Drones agrícolas — implantação

A página `servicos/drones.html` apresenta os serviços e prepara um pedido de orçamento para envio pelo próprio visitante no WhatsApp comercial já publicado. O formulário não faz upload nem envia contatos automaticamente. O KML/KMZ é anexado pelo cliente na conversa.

`radar-drones.html` usa `dados/radar_drones.json`, sem substituir o radar ambiental de MCE/PCA/PGRS. O robô em `scripts/atualizar_radar_drones.py` consulta PNCP e Compras.gov.br, com limites configurados em `dados/radar_drones_config.json`. O workflow de drones tem cron de duas horas e atualiza apenas seu próprio arquivo de dados; execução real depende das filas e das fontes.

## Critérios de publicação

- Serviço agrícola/florestal executado com drone, objeto compatível e prazo futuro explícito.
- Compra de equipamento, manutenção, cursos, filmagem, mapeamento isolado e prazos vencidos são bloqueados.
- Anexos não acessíveis, PDF escaneado, arquivo não suportado ou leitura parcial mantêm o processo em análise pendente.
- Oportunidade formal não equivale a habilitação da Ordone. Documentos, equipe, equipamentos e acervo precisam de conferência.
- Portais privados, BLL, Licitanet, Portal de Compras Públicas e prospecção privada automática continuam sem integração direta; essa limitação aparece no painel.
- Informações antigas não são reapresentadas como recém-verificadas. A interface também retira prazos expirados e sinaliza dados com mais de seis horas.

## Verificação

```sh
python -m unittest discover -s scripts -p 'test_radar_drones.py'
python scripts/atualizar_radar.py --self-test
node --check assets/drones.js
node --check assets/radar-drones.js
```

O robô não entra em contato com possíveis clientes e não envia propostas. A imagem utilizada é a fotografia de drone agrícola já publicada em `assets/drone-campo.webp`; não foi necessário acesso ao Google Fotos nesta atualização.
