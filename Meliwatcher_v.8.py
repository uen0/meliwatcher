"""
Buscador de libros en MLA. Descarga los codigos unicos de los articulos publicados y los almacena en un JSON y luego
compara las busquedas y te muestra las diferencias. Es algo que se podria mejorar, sobre todo la GUI, pero lo suspendo
porque descubri que exixte una API de mercadolibre que facilita mucho el trabajo de request y de categorizacion.
Cosas que tengo que recordar:
    - Los resultados de cada busqueda son inconsistentes. Hay repetidos y tambien escondidos.
    - Sospecho que la cantidad de articulos mostrados por busqueda es siempre la misma al menos que se agregue o se quite
    un articulo. Los articulos mostrados pueden cambiar pero la cantidad es siempre la misma. No estoy seguro.
    - Basandome en esa idea: se compara la busqueda con la base de datos unicamente cuando haya cambiado el numero de
    articulos por resultado. El error de esto es que -1 art. +1 art. no te muestra el nuevo articulo ya que el numero
    es el mismo.
    - A pesar de todo esto hay articulos viejos que aparecen despues de la busqueda numero n (a veces arriba de 6).
    - El archivo JSON no tiene una sincronizacion con lo publicado, por lo tanto nada se elimina al menos que se quite
    la busqueda completa.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import tkinter.scrolledtext as tkscrolled
import json
import tkinter
import tkinter.ttk as ttk
import webbrowser as web
import threading
import queue


def callback(url):
    web.open_new_tab(url)


class MainWindow(tkinter.Tk):
    def __init__(self, *args, **kwargs):
        tkinter.Tk.__init__(self, *args, **kwargs)
        self.resizable(False, False)
        self.version = 'Meliwatcher v.8'
        self.title(self.version)
        self.today = datetime.today()
        self.get_yesterday()
        self.lastupdate = self.yesterday - self.today
        self.url = f'https://libros.mercadolibre.com.ar/libros/usados/'

        # Tabs and frames.
        self.tabmanager = ttk.Notebook(self)
        self.mainframe = tkinter.Frame(self.tabmanager)
        self.advframe = tkinter.Frame(self.tabmanager)
        self.tabmanager.add(self.mainframe, text='Busqueda')
        self.tabmanager.add(self.advframe, text='Opciones')
        self.tabmanager.grid(row=0, column=0)

        # MAINFRAME.
        # Output frame and text.
        self.outputtext = tkscrolled.ScrolledText(self.mainframe, bg='white', height=11, wrap='word')
        self.outputtext.insert('end', 'Meliwatcher funciona comparando las busquedas en mercadolibre. La primera vez '
                                      'que se introduce una busqueda nueva se guardan todos los links del resultado. '
                                      ' A partir de la segunda busqueda se va a comparar la base de datos guardada con'
                                      ' el resultado de Mercadolibre.\n\n'
                                      f'La ultima actualizacion fue hace {str(abs(self.lastupdate))[:-10]}'
                                      f' horas.\n\n©uenok_2021.')
        self.outputtext.config(state='disabled')
        self.outputtext.grid(row=2, column=2, sticky='e', pady=2)

        # New articles
        self.container_frame = tkinter.LabelFrame(self.mainframe, width=900, text='Nuevas publicaciones')
        self.canvas = tkinter.Canvas(self.container_frame)
        self.new_articles_frame = tkinter.Frame(self.canvas)

        self.new_articles_frame.bind("<Configure>", lambda x: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((4, 4), window=self.new_articles_frame, anchor='nw', width=900)
        self.new_articles_frame_scrollbar = tkinter.Scrollbar(self.container_frame, orient="vertical", command=self.canvas.yview)

        self.canvas.configure(yscrollcommand=self.new_articles_frame_scrollbar.set, width=910, height=200)
        self.empty = tkinter.Label(self.new_articles_frame, text='- Nada aun -\n')

        self.container_frame.grid(row=3, column=0, columnspan=3, sticky='ne')
        self.new_articles_frame_scrollbar.pack(fill='y', side='right')
        self.canvas.pack(side='left', expand=True, fill='both')
        self.empty.pack()

        # Searchbar and listbox.
        self.searchbar = tkinter.Entry(self.mainframe)
        self.searchbar.grid(row=1, column=0, sticky='w', pady=2)
        self.listbox = tkinter.Listbox(self.mainframe)
        self.listbox_insert()
        self.listbox.grid(row=2, column=0, sticky='w', pady=2)

        # Threads
        self.one_go_thread = threading.Thread(target=self.one_go)
        self.go_thread = threading.Thread(target=self.go_search)

        # Buttons.
        self.enterbutton = tkinter.Button(self.mainframe, text='Ingresar', command=self.searchbar_text)
        self.enterbutton.grid(row=1, column=1, pady=2)
        self.deletebutton = tkinter.Button(self.mainframe, text='Eliminar', command=self.delete_title)
        self.deletebutton.grid(row=2, column=1, sticky='n', pady=10)
        self.gobutton = tkinter.Button(self.mainframe, text='Buscar todo', command=lambda: self.go_thread.start(), bg='green', fg='white')
        self.gobutton.grid(row=2, column=1, sticky='s')
        self.onlygo = tkinter.Button(self.mainframe, text='Buscar\nseleccionado', command=lambda: self.one_go_thread.start())
        self.onlygo.grid(row=2, column=1, pady=25)

        # ADVFRAME.

        # Checkbuttons and check_frame.
        self.check_var = tkinter.IntVar()
        self.check_var.set(0)
        self.check_frame = tkinter.LabelFrame(self.advframe, text='Condicion',)
        self.check_frame.pack()
        self.check_usado = tkinter.Checkbutton(self.check_frame, text='Usado', onvalue=0, var=self.check_var,
                                               command=self.set_url)
        self.check_usado.pack()
        self.check_nuevo = tkinter.Checkbutton(self.check_frame, text='Nuevo', onvalue=1, var=self.check_var,
                                               command=self.set_url)
        self.check_nuevo.pack()
        self.check_all = tkinter.Checkbutton(self.check_frame, text='Todo', onvalue=2, var=self.check_var,
                                             command=self.set_url)
        self.check_all.pack()

        # Categoria.
        self.category_label = tkinter.Label(self.advframe, text='Categoria')
        self.category_label.pack()
        self.category = 'libros'
        self.category_menu = ttk.Combobox(self.advframe, width=27, textvariable=self.category)
        self.category_menu['values'] = ['Libros', 'Computacion']
        self.category_menu.bind("<<ComboboxSelected>>", self.set_url)
        self.category_menu.pack()
        self.category_menu.current(0)


    def redirector(self, input_str):
        self.outputtext.config(state='normal')
        self.outputtext.insert('end', input_str + '\n')
        self.outputtext.config(state='disabled')
        self.outputtext.yview('end')
        self.update()

    def set_url(self, category='libros', condition='usado'):
        if self.check_var.get() == 1:
            condition = 'nuevo'
        elif self.check_var.get() == 2:
            condition = ''
        category = str(self.category_menu.get()).lower()
        self.url = f'https://{category}.mercadolibre.com.ar/{category}/{condition}/'
        print(self.url)

    # Function for listing all pages of that search result.
    def requester(self, url):
        all_title_hrefs = []
        while True:
            r = requests.get(url)
            html_data = BeautifulSoup(r.text, 'html.parser')

            href_list = [i['href'] for i in
                         html_data.find_all("a", class_="ui-search-item__group__element ui-search-link")]
            href_list = [i.split('_')[0] for i in href_list]
            for href in href_list:
                href = href.split('/')[-1].split('-')[1]
                all_title_hrefs.append(href)

            # Check if this is the last page
            pages_bar = html_data.find_all('a', class_='andes-pagination__link ui-search-link')
            try:
                if pages_bar[-1].text == 'Siguiente':
                    url = pages_bar[-1]['href']
                else:
                    break
            except IndexError:
                break

        try:
            self.one_go_thread.join()
        except RuntimeError:
            self.go_thread.join()
        finally:
            return all_title_hrefs

    def watcher(self, input_list, dict2):
        for title in input_list:
            # Number of links saved under title.
            if title in dict2.keys():
                self.redirector(f'\n\n > {title.capitalize()} ({len(dict2[title]["href_list"])} link/s saved):\n')
            else:
                self.redirector(f'\n\n > {title.capitalize()} (no links saved):\n')

            # Requesting title.
            self.redirector('\tRequesting...')

            all_title_hrefs = self.requester(self.url + title)



            # Checking record.
            self.after(100, self.redirector('\tChecking record...'))
            new_articles = []

            if title in dict2.keys():
                if len(all_title_hrefs) != dict2[title]['number']:
                    for hash in all_title_hrefs:
                        if hash not in dict2[title]['href_list'] and hash not in new_articles:
                            new_articles.append(hash)
                            new_title = tkinter.Label(self.new_articles_frame, text=f'{title}:')
                            new_title.pack()

                            new_article = 'https://articulo.mercadolibre.com.ar/MLA-' + hash
                            self.show_new_art(new_article)
                            self.redirector(f'\tThis new > {new_article}')

                    # Updating record.
                    self.redirector('\tUpdating record...')
                    href_list_copy = dict2[title]['href_list'].copy()
                    dict2[title]['number'] = len(all_title_hrefs)
                    updated_href_list = href_list_copy + all_title_hrefs
                    updated_href_list = set(updated_href_list)
                    dict2[title]['href_list'] = list(updated_href_list)

                else:
                    self.redirector(
                        '\tNothing new.')  # elif all_title_hrefs is a subset of dict2['href_list'] then nothing new.

            else:
                self.after(100, self.redirector(f'\tFirst time in register. {len(all_title_hrefs)} link/s saved.\n\n'))
                set_all_title_hrefs = set(all_title_hrefs)
                dict2[title] = {'number': len(all_title_hrefs), 'href_list': list(set_all_title_hrefs)}

            """
            Mercadolibre no es consistente con los resultados de las busquedas grandes.
            Los articulos listados a veces se repiten (por eso se transforma en un set() y luego en una list() otra vez
            ya que el set() no es serializable para JSON). Las busquedas tienen articulos que aparecen y desaparecen,
            supongo que son articulos que 'pueden interesarte'. Al no saber como diferenciar los articulos que son 
            directamente relacionados a la busqueda de los articulos que cambian, no pude determinar si una publi-
            cacion fue eliminada o no te la estan mostrando.
            La base de datos nunca se limpia (al menos que se elimine el titulo y se busque de nuevo.)
            """
            self.redirector('//')
        self.redirector('\tDone.')

    def searchbar_text(self):
        text20 = self.searchbar.get()
        listbox_titles = self.listbox.get(0, 'end')
        listbox_titles = [i.lower() for i in listbox_titles]
        if text20.lower() not in listbox_titles:
            self.listbox.insert('0', text20)
            self.searchbar.delete(0, 'end')

    def delete_title(self):
        self.listbox.delete('anchor')

    def go_search(self):
        user_list = self.listbox.get(0, 'end')
        user_list = [i.replace(' ', '-').lower() for i in user_list]

        self.outputtext.config(state='normal')
        self.outputtext.delete('1.0', 'end')
        self.outputtext.config(state='disabled')

        dict2 = self.read_file().copy()

        # The following two lines are in case the 'Date' key gets deleted.
        try:
            if dict2['Date']:
                dict2['Date'] = datetime.strftime(self.today, '%Y-%m-%d %H:%M:%S.%f')
        except KeyError:
            date_dict = {'Date': self.today}
            dict2 = {**date_dict, **dict2}

        # Clean the keywords you don't want anymore from the dictionary.
        for key in list(dict2)[1:]:
            if key not in user_list:
                self.redirector(f'{key} has been removed from the watchlist.')
                dict2.pop(key)

        self.watcher(user_list, dict2)
        self.write_all(dict2)

    def one_go(self):
        one = [self.listbox.get('anchor').replace(' ', '-').lower()]
        self.outputtext.config(state='normal')
        self.outputtext.delete('1.0', 'end')
        self.outputtext.config(state='disabled')

        dict2 = self.read_file().copy()
        dict2['Date'] = datetime.strftime(self.today, '%Y-%m-%d %H:%M:%S.%f')

        self.watcher(one, dict2)
        self.write_one(dict2)

    def read_file(self):
        file_read = open(r'/home/bme/PycharmProjects/meli_watcher/meli_log.json', 'r')
        try:
            dict1 = json.load(file_read)
            self.yesterday = datetime.strptime(dict1['Date'], '%Y-%m-%d %H:%M:%S.%f')
            file_read.close()
        except json.decoder.JSONDecodeError:
            dict1 = {}
            file_read.close()

        return dict1

    def write_all(self, dict2):
        file_write = open(r'/home/bme/PycharmProjects/meli_watcher/meli_log.json', 'w')
        json.dump(dict2, file_write)
        file_write.close()

    def write_one(self, dict2):
        # This line avoids removing keywords from the dict but adds them even though they are repeated.
        dict_to_json = {**self.read_file().copy(), **dict2}

        file_write = open(r'/home/bme/PycharmProjects/meli_watcher/meli_log.json', 'w')
        json.dump(dict_to_json, file_write)
        file_write.close()

    def listbox_insert(self):
        for i in list(self.read_file())[1:]:
            self.listbox.insert(0, i.replace('-', ' ').capitalize())

    def show_new_art(self, new_art):
        self.empty.destroy()
        r = requests.get(new_art)
        data = BeautifulSoup(r.text, 'html.parser')
        title = data.find('h1', class_="ui-pdp-title").text
        price = data.find('span', class_="price-tag-amount").text
        new_title = tkinter.Label(self.new_articles_frame, text=f"{title} - {price}", fg='blue', cursor='hand2')
        new_title.pack()
        new_title.bind("<Button-1>", lambda x: callback(new_art))

    def get_yesterday(self):
        if 'Date' in self.read_file():
            self.yesterday = datetime.strptime(self.read_file()['Date'], '%Y-%m-%d %H:%M:%S.%f')
        else:
            self.yesterday = self.today


if __name__ == "__main__":
    window = MainWindow()
    window.mainloop()


"""
    Next version:
        -   Change GUI palette.
        -   Geography fine-tuning.
        -   Stop process button.
        -   Clean all button with a popup window "are you sure?"
        -   Dealing with hyperlinks. Opening chrome, etc.
        -   Pasar todo al espanol.
"""


