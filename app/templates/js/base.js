// Code needed to make the base template work properly
// All of the following code will only run when the page is ready
//  (the $() is short for $(document).ready())

$(function(){

    $('#a_check_gps').on('click', function(event){
        console.log('check gps got clicked.');
        $.getJSON($SCRIPT_ROOT + '/_check_gps',
                  {},
                  function(data){
                      console.log(data);
                      alert('Hello');
                      return true;
                  }
            );
        return true;
    });

});
