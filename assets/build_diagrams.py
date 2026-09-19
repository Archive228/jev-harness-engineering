# -*- coding: utf-8 -*-
from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
C = {'bg':'#FBF8F2','paper':'#FFFFFF','ink':'#26302F','muted':'#66716C','line':'#D8DCD4','soft':'#F1F2EC','accent':'#E47254','pale':'#FFF0E8'}
FONT = "Arial, Helvetica, sans-serif"
MONO = "Menlo, Consolas, monospace"

class SVG:
    def __init__(self, width, height, title, desc):
        self.width, self.height = width, height
        self.s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">', f'<title id="title">{escape(title)}</title>', f'<desc id="desc">{escape(desc)}</desc>', '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L8,4.5 L0,9" fill="#66716C"/></marker></defs>']
        self.rect(0,0,width,height,fill=C['bg'],radius=0)
    def rect(self,x,y,w,h,fill=None,stroke=None,radius=20,sw=1.5):
        self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill or C["paper"]}"'+(f' stroke="{stroke}" stroke-width="{sw}"' if stroke else '')+'/>')
    def text(self,x,y,t,size=24,fill=None,weight=400,anchor='start',font=FONT):
        self.s.append(f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" fill="{fill or C["ink"]}" text-anchor="{anchor}">{escape(t)}</text>')
    def lines(self,x,y,lines,size=24,dy=34,**kwargs):
        for i,t in enumerate(lines): self.text(x,y+i*dy,t,size=size,**kwargs)
    def line(self,x1,y1,x2,y2,stroke=None,sw=2,arrow=False,dash=None):
        self.s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke or C["line"]}" stroke-width="{sw}"'+(' marker-end="url(#arrow)"' if arrow else '')+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
    def path(self,d,stroke=None,sw=2,arrow=False):
        self.s.append(f'<path d="{d}" fill="none" stroke="{stroke or C["line"]}" stroke-width="{sw}"'+(' marker-end="url(#arrow)"' if arrow else '')+'/>')
    def circle(self,x,y,r,fill,stroke=None):
        self.s.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"'+(f' stroke="{stroke}" stroke-width="2"' if stroke else '')+'/>')
    def tag(self,x,y,w,t,fill=None,ink=None,size=18):
        self.rect(x,y,w,34,fill=fill or C['soft'],radius=17)
        self.text(x+w/2,y+23,t,size=size,fill=ink or C['muted'],weight=700,anchor='middle')
    def head(self,n,label,title,subtitle):
        self.text(64,64,f'{n}  /  {label.upper()}',size=17,fill=C['muted'],weight=700)
        self.text(64,126,title,size=42,weight=700)
        self.text(64,172,subtitle,size=23,fill=C['muted'])
    def save(self,name):
        self.s.append('</svg>')
        xml='\n'.join(self.s)
        ET.fromstring(xml)
        (ROOT/name).write_text(xml,encoding='utf-8')

s=SVG(1480,760,'Как работает интерфейс Jev','Приложение передаёт состояние и вопросы. Jev возвращает типизированные ответы Choice, Score и Noul. Код приложения определяет следующее действие. Схема показывает API-контракт, а не внутреннее устройство нейросети.')
s.head('01','Интерфейс','Смысл → типизированный ответ → действие','Вы задаёте пространство ответов. Jev оценивает смысл. Программа выполняет действие.')
s.rect(64,232,312,352,stroke=C['line'])
s.tag(88,256,118,'ВХОД')
s.text(88,334,'State',size=30,weight=700)
s.lines(88,374,['Текст, JSON, факты','и нужный контекст'],size=23,dy=32)
s.line(88,431,352,431)
s.text(88,477,'Вопросы',size=30,weight=700)
s.lines(88,517,['Инструкции + критерии','для каждого ответа'],size=22,dy=31)
s.line(382,408,430,408,stroke=C['muted'],arrow=True)
s.rect(440,296,228,224,fill=C['pale'],stroke=C['accent'],sw=2)
s.text(554,380,'Jev',size=64,weight=700,anchor='middle')
s.lines(554,427,['Оценивает','заданные вопросы'],size=22,dy=31,anchor='middle')
s.line(676,408,724,408,stroke=C['muted'],arrow=True)
s.rect(734,232,326,352,stroke=C['line'])
s.tag(758,256,126,'ОТВЕТ')
s.text(758,337,'Choice',size=28,weight=700)
s.text(758,370,'Вариант из списка',size=22,fill=C['muted'])
s.text(758,430,'Score',size=28,weight=700)
s.text(758,463,'Положение на шкале',size=22,fill=C['muted'])
s.text(758,523,'Noul',size=28,weight=700)
s.text(758,556,'Вероятность «да»',size=22,fill=C['muted'])
s.line(1068,408,1114,408,stroke=C['muted'],arrow=True)
s.rect(1124,232,292,352,fill=C['soft'])
s.tag(1148,256,152,'ПРИЛОЖЕНИЕ',fill=C['paper'])
s.text(1148,339,'Обычный код',size=28,weight=700)
s.lines(1148,391,['Сохранить категорию','Отсортировать очередь','Выбрать обработчик','Запустить проверку'],size=21,dy=42)
s.rect(64,626,1352,80,fill=C['pale'])
s.text(90,660,'Тип ответа ограничен контрактом; правильность смыслового решения проверяют отдельно.',size=23,weight=700)
s.text(90,689,'Эта схема описывает обмен данными с API, а не внутреннюю архитектуру модели.',size=19,fill=C['muted'])
s.save('01-jev-interface.svg')

s=SVG(1480,1080,'Три примитива Jev на одном сообщении','Одинаковое сообщение об ошибке экспорта PDF передаётся трём независимым вопросам. Choice выбирает категорию, Score оценивает влияние на заданной шкале от нуля до двух, Noul оценивает вероятность того, что рабочий обход явно указан. Числа вероятностей и результаты живого API не показаны.')
s.head('02','Три примитива','Один state. Три разных вопроса.','Ниже — заданные критерии и формы ответов, без выдуманных результатов API.')
s.rect(64,211,1352,140,stroke=C['line'])
s.tag(88,232,166,'ОБЩИЙ STATE')
s.lines(280,252,['«В Safari экспорт PDF завершается ошибкой. В Chrome тот же документ', 'экспортируется. Сейчас пользуюсь Chrome, но хочу вернуть экспорт в Safari».'],size=25,dy=40)
for x in [276,740,1204]:
    s.line(x,351,x,396,stroke=C['muted'],arrow=True)

xs=[64,528,992]
for i,x in enumerate(xs): s.rect(x,406,424,572,stroke=C['line'])
# Choice
x=xs[0]
s.tag(x+24,430,108,'CHOICE',fill=C['pale'],ink=C['accent'])
s.text(x+24,505,'Какой вариант подходит?',size=26,weight=700)
s.lines(x+24,550,['К какой категории','относится обращение?'],size=24,dy=33)
for y,label in [(615,'export  ·  Экспорт'),(657,'account  ·  Аккаунт'),(699,'payment  ·  Оплата'),(741,'other  ·  Другое')]:
    s.circle(x+35,y-7,6,C['bg'],stroke=C['line'])
    s.text(x+53,y,label,size=22)
s.line(x+24,773,x+400,773)
s.text(x+24,810,'Форма ответа',size=18,fill=C['muted'],weight=700)
s.lines(x+24,843,['ID + распределение', '+ confidence'],size=24,dy=32,weight=700)
s.text(x+24,930,'Код: выбрать очередь',size=22,fill=C['muted'])
# Score
x=xs[1]
s.tag(x+24,430,108,'SCORE',fill=C['pale'],ink=C['accent'])
s.text(x+24,505,'Где случай на шкале?',size=26,weight=700)
s.lines(x+24,550,['Насколько проблема','мешает выполнить задачу?'],size=24,dy=33)
s.line(x+45,623,x+373,623,stroke=C['ink'],sw=3)
for pos,v in [(x+45,'0'),(x+209,'1'),(x+373,'2')]:
    s.circle(pos,623,6,C['accent'])
    s.text(pos,656,v,size=23,anchor='middle',weight=700)
s.lines(x+24,694,['0  Косметический дефект','1  Сломано, есть обход','2  Заблокировано, обхода нет'],size=21,dy=31)
s.line(x+24,773,x+400,773)
s.text(x+24,810,'Форма ответа',size=18,fill=C['muted'],weight=700)
s.lines(x+24,843,['Оценка между уровнями', '+ распределение + confidence'],size=22,dy=32,weight=700)
s.text(x+24,930,'Код: сортировать по влиянию',size=22,fill=C['muted'])
# Noul
x=xs[2]
s.tag(x+24,430,108,'NOUL',fill=C['pale'],ink=C['accent'])
s.text(x+24,505,'Верно ли утверждение?',size=26,weight=700)
s.lines(x+24,550,['В сообщении явно указан','рабочий обход проблемы?'],size=24,dy=33)
s.line(x+45,623,x+373,623,stroke=C['ink'],sw=3)
for pos,v in [(x+45,'0'),(x+209,'0.5'),(x+373,'1')]:
    s.circle(pos,623,6,C['bg'],stroke=C['ink'])
    s.text(pos,656,v,size=23,anchor='middle',weight=700)
s.text(x+45,690,'«нет»',size=19,anchor='middle',fill=C['muted'])
s.text(x+373,690,'«да»',size=19,anchor='middle',fill=C['muted'])
s.text(x+209,734,'0.5 ≈ неопределённость',size=23,anchor='middle',fill=C['muted'])
s.line(x+24,773,x+400,773)
s.text(x+24,810,'Форма ответа',size=18,fill=C['muted'],weight=700)
s.lines(x+24,843,['Вероятность «да»: 0…1', 'Отдельного confidence нет'],size=22,dy=32,weight=700)
s.text(x+24,930,'Код: решить, нужно ли уточнение',size=21,fill=C['muted'])
s.text(64,1025,'В одном запросе вопросы независимы. Ответы объединяет код приложения.',size=24,weight=700)
s.save('02-three-primitives.svg')

s=SVG(1480,1160,'Jev в трёх мини-сборках','Первая сборка использует Noul для смысловой оценки свидетельств. Вторая использует Choice для выбора необязательной диагностики из реестра. Третья соединяет их с worker и программными правилами переходов. Обязательные проверки, лимиты и решение о завершении задаются кодом.')
s.head('03','Три мини-сборки','Три инструмента. Один контракт с Jev.','Вход → узкий смысловой вопрос → ответ → наблюдаемый результат.')
rows=[(219,'01','Evidence report','Критерии, snapshot,','результаты команд','Noul','Связано ли свидетельство','с нужным критерием?','evidence-report.json','passed · failed · unverified','Noul — аннотация. Статусы задаёт код по свежим результатам тестов.'),(502,'02','Next-check router','Провал проверки,','реестр диагностики','Choice','Какая дополнительная','проверка полезна сейчас?','next-check.json','ID из реестра / отказ','Обязательные проверки запускает код. Jev выбирает дополнительную диагностику.'),(785,'03','Bounded loop','Новый snapshot,','отчёт и лимиты','Noul + Choice','Связь с критерием?','Что проверить дальше?','run-report.md','complete / stopped + причина','Код завершает цикл только при выполнении условий приёмки; лимиты ограничивают попытки.')]
for y,n,title,a,b,primitive,q1,q2,out,result,caption in rows:
    s.rect(64,y,1352,252,stroke=C['line'])
    s.tag(88,y+20,56,n,fill=C['soft'])
    s.text(159,y+46,title,size=28,weight=700)
    s.lines(88,y+105,[a,b],size=25,dy=34)
    s.line(406,y+118,474,y+118,stroke=C['muted'],arrow=True)
    s.rect(488,y+70,420,108,fill=C['pale'])
    s.text(511,y+101,f'Jev · {primitive}',size=20,fill=C['accent'],weight=700)
    s.lines(511,y+134,[q1,q2],size=22,dy=29)
    s.line(922,y+118,986,y+118,stroke=C['muted'],arrow=True)
    s.text(1004,y+105,out,size=23,font=MONO,weight=700)
    s.text(1004,y+144,result,size=20,fill=C['muted'])
    s.line(88,y+196,1392,y+196)
    s.text(88,y+229,caption,size=21,fill=C['muted'])
s.text(64,1100,'Jev возвращает оценку или ID. Проверки, исправления и остановку выполняет приложение.',size=24,weight=700)
s.save('03-three-builds.svg')

s=SVG(1480,1290,'Трасса демонстрационного запуска','Явно офлайн-сценарий: требование поиска по описанию сначала не подтверждено. Обязательная проверка C2 выявляет ошибку. Подготовленный ответ router выбирает диагностическую проверку D2. Worker исправляет реализацию, создаётся новый snapshot, оба обязательных теста проходят, программная политика завершает запуск. Схема не показывает результаты живого API Jev.')
s.head('04','Разбор одного запуска','От «не проверено» до подтверждённого результата','Офлайн-demo: ответы judge и действие worker подготовлены. Живой API Jev здесь не вызывается.')
s.line(98,274,98,1120,stroke=C['line'],sw=3)
steps=[
('01','Свидетельства','R2: поиск по описанию','Есть заявление worker; актуального результата C2 ещё нет.','UNVERIFIED'),
('02','Обязательный тест','Код запускает C2','Поиск по описанию не находит задачу. Появился факт сбоя.','FAIL'),
('03','Доп. диагностика','Демонстрационный router → D2','Проверка запроса: используется только поле title.','НОВЫЙ ФАКТ'),
('04','Исправление','Worker обновляет реализацию','Поиск учитывает title ИЛИ description.','НОВЫЙ КОД'),
('05','Повторная проверка','Новый snapshot → C1 и C2','Результаты прежней версии не подтверждают текущий код.','PASS + PASS'),
('06','Правило завершения','Все обязательные условия выполнены','Программа сохраняет отчёт и останавливает цикл.','COMPLETE')]
for i,(n,role,title,body,status) in enumerate(steps):
    y=220+i*158
    s.circle(98,y+55,26,C['pale'],stroke=C['accent'])
    s.text(98,y+63,n,size=21,weight=700,anchor='middle')
    s.rect(153,y,1263,132,stroke=C['line'])
    s.text(181,y+30,role.upper(),size=15,weight=700,fill=C['muted'])
    s.text(181,y+67,title,size=28,weight=700)
    s.text(181,y+107,body,size=23,fill=C['muted'])
    w=205
    s.tag(1187,y+43,w,status,fill=C['pale'] if i in [2,5] else C['soft'],ink=C['accent'] if i in [2,5] else C['ink'],size=17)
s.rect(64,1208,1352,48,fill=C['pale'],radius=12)
s.text(88,1239,'Нет результата ≠ провал. PASS старой версии ≠ PASS текущей. Решение Jev ≠ результат команды.',size=22,weight=700)
s.save('04-run-trace.svg')

print('\n'.join(str(p) for p in sorted(ROOT.glob('*.svg'))))
