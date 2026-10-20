function adicionaParametrosPadrao(d) { return $.extend({}, d, {}); }
	
function renderizadorDeCelulaPadrao(data, type, full, meta) { return data; }

function formatadorDeCelulaPadrao(nTd, sData, oData, iRow, iCol) {
	var header = $('#td').DataTable().column(iCol).header();
	
	if($(header).hasClass("aoCentro"))
		$(nTd).addClass("text-center");
	else if($(header).hasClass("aEsquerda"))
		$(nTd).addClass("text-left");
	else if($(header).hasClass("aDireita"))
		$(nTd).addClass("text-right");
}
function setCurrentPage(obj) {
	var table = $('#td').DataTable();
	var info = table.page.info();
	var page = parseInt(obj.value);
	
	if(page <= 0)
		page = 1;
	else if(page > info.pages)
		page = info.pages;
	
	obj.value = page;
	table.page(parseInt(page - 1)).draw(false);
}
var tabelaDinamica = $('#td').DataTable({
	"dom": '<"top row text-left"<"col-sm-5"i><"col-sm-5"p><"col-sm-2 text-right gotoPage">>rt<"bottom row"<"col-sm-12 export"><"col-sm-10"fp><"col-sm-2 text-right gotoPage">><"clear">',
	"pageLength": 10,
	"processing": true,
	"serverSide" : true,
    "ajax": {
        "url": nmControllerParaPaginacao + "Ajax",
        "data": function(d) {
        	try {
				return adicionaParametros(d);
			} catch (e) {
				return adicionaParametrosPadrao(d);
			}
        },
        "dataSrc": "paginacao.registrosAsJSONArray",
        "type": "POST"
    },
	"searching": false,
    "order": [[ 1, "asc" ]],
	"columnDefs": [
		{ "fnCreatedCell": function(nTd, sData, oData, iRow, iCol) {
			try {
				formatadorDeCelula(nTd, sData, oData, iRow, iCol);
			} catch (e) {
				formatadorDeCelulaPadrao(nTd, sData, oData, iRow, iCol);
			}
		}, 'aTargets': ['_all'] },
		{ "mRender": function(data, type, full, meta) {
			try {
				return renderizadorDeCelula(data, type, full, meta);
			} catch (e) {
				return renderizadorDeCelulaPadrao(data, type, full, meta);
			}
		}, 'aTargets': ['_all'] }
	],
	"language": {
	    "decimal":        ",",
	    "emptyTable":     "Sem registros",
	    "info":           "Exibindo registro _START_ at&eacute; _END_ do total de _TOTAL_",
	    "infoEmpty":      "",
	    "infoFiltered":   "(filtrados de _MAX_ registros)",
	    "infoPostFix":    "",
	    "thousands":      ".",
	    "lengthMenu":     "Exibindo _MENU_ registros por p&atilde;gina",
	    "loadingRecords": "Carregando...",
	    "processing":     "Processando...",
	    "search":         "Pesquisa:",
	    "zeroRecords":    "Resultado n&atilde;o encontrado",
	    "paginate": {
	        "first":      "Primeira",
	        "last":       "&Uacute;ltima",
	        "next":       "Pr&oacute;xima",
	        "previous":   "Anterior"
	    },
	    "aria": {
	        "sortAscending":  ": clique para ordenar ascendente",
	        "sortDescending": ": clique para ordenar descendente"
	    }
	}
});
if(pesquisaVazia == "true")
	$("#mensagemPesquisaVazia").removeClass("oculto");

if(pesquisaPaginaUnica == "true")
	$(".dataTables_paginate").remove();
else
	$(".gotoPage").attr("style", "padding-top: 2px;").html("<label style='padding-right:10px'>Ir p/ pg</label><input type='text' class='form-control' style='width: 50px;' onchange='setCurrentPage(this);'>");

$(".export").addClass("text-left");
$(".exportlinks a").addClass("btn btn-default");
$(".exportlinks a span.pdf").text(" PDF").addClass("fa fa-file-pdf-o");
$(".exportlinks a span.csv").text(" CSV").addClass("fa fa-file-text-o");
$(".exportlinks a span.excel").text(" EXCEL").addClass("fa fa-file-excel-o");
$(".exportlinks a span.xml").text(" XML").addClass("fa fa-file-code-o");

var exports = jQuery(".exportlinks").html();
jQuery(".pagelinks").remove();
jQuery(".pagebanner").remove();
jQuery(".exportlinks").remove();
jQuery("div.export").html(exports);

if($("#td_wrapper") && $("#td_wrapper").offset() && !$("#mensagem .alert").is(":visible"))	
	$("html, body").animate({ scrollTop: $("#td_wrapper").offset().top - 50 }, 600);